import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.security import signing_keys

REDIRECT = "http://hr.local/callback"


def login(c: TestClient, username: str, password: str):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize(c: TestClient, client_id: str, challenge: str, nonce: str = "n-1"):
    return c.get("/oauth/authorize", params={
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": "openid profile email", "state": "xyz", "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }, follow_redirects=False)


def test_full_sso_flow(client: TestClient):
    assert login(client, "admin", "test-admin-pass").status_code == 200

    # Admin registers a system with roles and a user.
    created = client.post("/api/admin/applications", json={
        "name": "HR", "redirect_uris": [REDIRECT], "home_url": "http://hr.local/",
    })
    assert created.status_code == 201, created.text
    hr = created.json()
    secret = hr["client_secret"]
    assert secret
    viewer = client.post(f"/api/admin/applications/{hr['id']}/roles", json={"name": "viewer"}).json()
    editor = client.post(f"/api/admin/applications/{hr['id']}/roles", json={"name": "editor"}).json()

    created_user = client.post("/api/admin/users", json={
        "username": "alice", "email": "alice@corp.example.com", "password": "alice-pass-1",
    })
    assert created_user.status_code == 201, created_user.text
    alice = created_user.json()

    # Alice signs in to the portal in her own browser.
    with TestClient(app) as browser:
        assert login(browser, "alice", "wrong-password").status_code == 401

        # Not signed in yet -> sent to the portal login page.
        verifier, challenge = pkce()
        r = authorize(browser, "hr", challenge)
        assert r.status_code == 302 and urlparse(r.headers["location"]).path == "/login"

        assert login(browser, "alice", "alice-pass-1").status_code == 200

        # Signed in but no role in HR -> access denied, no code.
        r = authorize(browser, "hr", challenge)
        assert "/access-denied" in r.headers["location"]

        # Admin grants a role.
        assert client.put(f"/api/admin/users/{alice['id']}/roles",
                          json={"role_ids": [viewer["id"], editor["id"]]}).status_code == 200

        r = authorize(browser, "hr", challenge)
        loc = urlparse(r.headers["location"])
        assert f"{loc.scheme}://{loc.netloc}{loc.path}" == REDIRECT
        params = parse_qs(loc.query)
        assert params["state"] == ["xyz"]
        code = params["code"][0]

        apps = browser.get("/api/me/applications").json()
        assert apps[0]["name"] == "HR" and apps[0]["roles"] == ["editor", "viewer"]

    # The HR backend exchanges the code.
    bad = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "code_verifier": verifier, "client_id": "hr", "client_secret": "wrong",
    })
    assert bad.status_code == 401

    tok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "code_verifier": verifier,
    }, auth=("hr", secret))
    assert tok.status_code == 200, tok.text
    tokens = tok.json()

    # Tokens verify against the published JWKS and carry the roles.
    jwk = client.get("/oauth/jwks").json()["keys"][0]
    key = jwt.PyJWK(jwk).key
    id_token = jwt.decode(tokens["id_token"], key, algorithms=["RS256"], audience="hr", issuer="http://testserver")
    assert id_token["preferred_username"] == "alice"
    assert id_token["roles"] == ["editor", "viewer"]
    assert id_token["nonce"] == "n-1"

    # Codes are single use.
    replay = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier,
    }, auth=("hr", secret))
    assert replay.json()["error"] == "invalid_grant"

    info = client.get("/oauth/userinfo", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert info.json()["roles"] == ["editor", "viewer"]

    # Role change shows up on refresh.
    client.put(f"/api/admin/users/{alice['id']}/roles", json={"role_ids": [viewer["id"]]})
    refreshed = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
    }, auth=("hr", secret)).json()
    claims = signing_keys.verify(refreshed["access_token"], audience="hr")
    assert claims["roles"] == ["viewer"]

    # Old refresh token was rotated out.
    again = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
    }, auth=("hr", secret))
    assert again.json()["error"] == "invalid_grant"

    # Deactivating the user cuts off refresh.
    client.patch(f"/api/admin/users/{alice['id']}", json={"is_active": False})
    cut = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": refreshed["refresh_token"],
    }, auth=("hr", secret))
    assert cut.json()["error"] == "invalid_grant"


def test_unregistered_redirect_uri_is_rejected(client: TestClient):
    r = client.get("/oauth/authorize", params={
        "client_id": "hr", "redirect_uri": "http://evil.test/cb", "response_type": "code",
    }, follow_redirects=False)
    assert r.status_code == 400


def test_non_admin_cannot_use_admin_api():
    with TestClient(app) as browser:
        browser.post("/api/admin/users")  # unauthenticated
        assert browser.get("/api/admin/users").status_code == 401


def test_overview_and_access_summary(client: TestClient):
    # Runs after test_full_sso_flow: alice holds HR "viewer" and is disabled.
    users = {u["username"]: u for u in client.get("/api/admin/users").json()}
    assert users["alice"]["access"] == [{"application_id": 1, "application_name": "HR", "roles": ["viewer"]}]
    assert client.get("/api/admin/applications").json()[0]["member_count"] == 1

    ov = client.get("/api/admin/overview").json()
    assert ov["users_total"] == 2 and ov["users_active"] == 1
    assert ov["systems"][0]["member_count"] == 1 and ov["systems"][0]["role_count"] == 2
    assert ov["failed_sign_ins_24h"] >= 1 and ov["sso_grants_24h"] >= 1 and ov["denied_24h"] >= 1


def test_permissions_flow_into_tokens(client: TestClient):
    fin = client.post("/api/admin/applications", json={
        "name": "Fin", "redirect_uris": [REDIRECT],
    }).json()
    secret, app_id = fin["client_secret"], fin["id"]
    clerk = client.post(f"/api/admin/applications/{app_id}/roles", json={"name": "clerk"}).json()
    view = client.post(f"/api/admin/applications/{app_id}/permissions",
                       json={"name": "invoices.view", "description": "View invoices"}).json()
    pay = client.post(f"/api/admin/applications/{app_id}/permissions", json={"name": "invoices.pay"}).json()
    assert client.post(f"/api/admin/applications/{app_id}/permissions",
                       json={"name": "invoices.view"}).status_code == 409

    r = client.put(f"/api/admin/applications/{app_id}/role-permissions",
                   json={"roles": {str(clerk["id"]): [view["id"]]}})
    assert r.status_code == 200, r.text
    assert r.json()["roles"][0]["permission_ids"] == [view["id"]]

    # Can't map another application's permission.
    assert client.put(f"/api/admin/applications/{app_id}/role-permissions",
                      json={"roles": {str(clerk["id"]): [999]}}).status_code == 400

    bob = client.post("/api/admin/users", json={
        "username": "bob", "email": "bob@corp.example.com", "password": "bob-pass-12",
    }).json()
    client.put(f"/api/admin/users/{bob['id']}/roles", json={"role_ids": [clerk["id"]]})

    with TestClient(app) as browser:
        login(browser, "bob", "bob-pass-12")
        verifier, challenge = pkce()
        loc = authorize(browser, "fin", challenge).headers["location"]
        code = parse_qs(urlparse(loc).query)["code"][0]
        apps = browser.get("/api/me/applications").json()
        assert apps[0]["permissions"] == ["invoices.view"]

    tokens = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier,
    }, auth=("fin", secret)).json()
    assert signing_keys.verify(tokens["id_token"], audience="fin")["permissions"] == ["invoices.view"]

    # Granting the role another permission reaches the system on refresh.
    client.put(f"/api/admin/applications/{app_id}/role-permissions",
               json={"roles": {str(clerk["id"]): [view["id"], pay["id"]]}})
    refreshed = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
    }, auth=("fin", secret)).json()
    claims = signing_keys.verify(refreshed["access_token"], audience="fin")
    assert claims["permissions"] == ["invoices.pay", "invoices.view"]
    assert claims["roles"] == ["clerk"]

    info = client.get("/oauth/userinfo", headers={"Authorization": f"Bearer {refreshed['access_token']}"}).json()
    assert info["permissions"] == ["invoices.pay", "invoices.view"]

    # Deleting a permission removes it from every role.
    assert client.delete(f"/api/admin/applications/{app_id}/permissions/{pay['id']}").status_code == 204
    assert client.get(f"/api/admin/applications/{app_id}").json()["roles"][0]["permission_ids"] == [view["id"]]


def test_delete_application_with_granted_permissions_and_members(client: TestClient):
    """role_permissions has no DB-level cascade on permission_id (SQL Server allows only one cascade path),
    so the ORM must clean up the association rows itself. Also checks non-Latin text round-trips."""
    from app.database import SessionLocal
    from app.models import role_permissions, user_roles

    ops = client.post("/api/admin/applications", json={
        "name": "Ops ကုန်သွယ်ရေး", "redirect_uris": [REDIRECT],
    }).json()
    app_id = ops["id"]
    assert client.get(f"/api/admin/applications/{app_id}").json()["name"] == "Ops ကုန်သွယ်ရေး"
    lead = client.post(f"/api/admin/applications/{app_id}/roles", json={"name": "lead"}).json()
    perm = client.post(f"/api/admin/applications/{app_id}/permissions", json={"name": "ops.run"}).json()
    client.put(f"/api/admin/applications/{app_id}/role-permissions", json={"roles": {str(lead["id"]): [perm["id"]]}})
    user = client.post("/api/admin/users", json={
        "username": "ops.user", "email": "ops.user@corp.example.com", "password": "ops-pass-12",
    }).json()
    client.put(f"/api/admin/users/{user['id']}/roles", json={"role_ids": [lead["id"]]})

    assert client.delete(f"/api/admin/applications/{app_id}").status_code == 204
    with SessionLocal() as db:
        assert db.execute(role_permissions.select().where(role_permissions.c.role_id == lead["id"])).first() is None
        assert db.execute(user_roles.select().where(user_roles.c.role_id == lead["id"])).first() is None
    assert client.get(f"/api/admin/users/{user['id']}").json()["role_ids"] == []


def test_client_id_is_generated_from_the_name(client: TestClient):
    """Admins don't type a client ID: it's made from the name, unique, and can't be supplied."""
    made = lambda name: client.post("/api/admin/applications", json={  # noqa: E731
        "name": name, "redirect_uris": [REDIRECT], "client_id": "chosen-by-admin"}).json()
    first = made("Promotion Approval Form")
    assert first["client_id"] == "promotion-approval-form"          # the supplied value is ignored
    assert made("Promotion  Approval / Form!")["client_id"] == "promotion-approval-form-2"
    assert made("ကုန်သွယ်ရေး")["client_id"] == "system"               # no Latin letters in the name
    assert made("X")["client_id"] == "x-system"                       # too short on its own
    # It never changes afterwards, even when the system is renamed.
    renamed = client.patch(f"/api/admin/applications/{first['id']}", json={"name": "PAF"}).json()
    assert renamed["client_id"] == "promotion-approval-form"


def test_silent_sign_in_prompt_none():
    """prompt=none never shows portal UI: it returns a code or an error to the system."""
    _, challenge = pkce()
    params = {"client_id": "hr", "redirect_uri": REDIRECT, "response_type": "code", "scope": "openid",
              "state": "st", "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "none"}
    with TestClient(app) as browser:
        r = browser.get("/oauth/authorize", params=params, follow_redirects=False)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert r.headers["location"].startswith(REDIRECT) and q["error"] == ["login_required"] and q["state"] == ["st"]

        # Signed in but no role in HR: access_denied goes back to the system, not the portal page.
        assert login(browser, "bob", "bob-pass-12").status_code == 200
        r = browser.get("/oauth/authorize", params=params, follow_redirects=False)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert r.headers["location"].startswith(REDIRECT) and q["error"] == ["access_denied"]


def test_web_origins_cors_and_public_client(client: TestClient):
    spa_origin, spa_redirect = "http://spa.example.com", "http://spa.example.com/"
    bad = client.post("/api/admin/applications", json={
        "name": "Bad SPA", "confidential": False,
        "redirect_uris": [spa_redirect], "web_origins": ["http://spa.example.com/path"],
    })
    assert bad.status_code == 422  # origins can't have a path

    spa = client.post("/api/admin/applications", json={
        "name": "SPA", "confidential": False,
        "redirect_uris": [spa_redirect], "web_origins": ["HTTP://spa.example.com/"],
    }).json()
    assert spa["client_secret"] is None and spa["web_origins"] == [spa_origin]  # normalised
    role = client.post(f"/api/admin/applications/{spa['id']}/roles", json={"name": "user"}).json()

    # Registered origin: preflight and response carry CORS headers.
    pre = client.options("/oauth/token", headers={
        "Origin": spa_origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == spa_origin
    disc = client.get("/.well-known/openid-configuration", headers={"Origin": spa_origin})
    assert disc.headers["access-control-allow-origin"] == spa_origin

    # Unknown origin, or a portal-internal endpoint: no CORS.
    assert client.options("/oauth/token", headers={
        "Origin": "http://evil.example.com", "Access-Control-Request-Method": "POST"}).status_code == 403
    assert "access-control-allow-origin" not in client.get(
        "/.well-known/openid-configuration", headers={"Origin": "http://evil.example.com"}).headers
    assert "access-control-allow-origin" not in client.get(
        "/api/health", headers={"Origin": spa_origin}).headers

    # Full public-client flow: PKCE instead of a secret, then refresh.
    carol = client.post("/api/admin/users", json={
        "username": "carol", "email": "carol@corp.example.com", "password": "carol-pass-1"}).json()
    client.put(f"/api/admin/users/{carol['id']}/roles", json={"role_ids": [role["id"]]})
    with TestClient(app) as browser:
        login(browser, "carol", "carol-pass-1")
        verifier, challenge = pkce()
        r = browser.get("/oauth/authorize", params={
            "client_id": "spa", "redirect_uri": spa_redirect, "response_type": "code", "scope": "openid",
            "state": "s", "code_challenge": challenge, "code_challenge_method": "S256"}, follow_redirects=False)
        code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    tok = client.post("/oauth/token", headers={"Origin": spa_origin}, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": spa_redirect,
        "code_verifier": verifier, "client_id": "spa"})
    assert tok.status_code == 200 and tok.headers["access-control-allow-origin"] == spa_origin
    refreshed = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": tok.json()["refresh_token"], "client_id": "spa"})
    assert refreshed.status_code == 200
    assert signing_keys.verify(refreshed.json()["access_token"], audience="spa")["roles"] == ["user"]

    # Removing the origin takes effect immediately.
    client.patch(f"/api/admin/applications/{spa['id']}", json={"web_origins": []})
    assert "access-control-allow-origin" not in client.get(
        "/.well-known/openid-configuration", headers={"Origin": spa_origin}).headers


def test_code_challenge_method_defaults_to_s256():
    """Apps may send just client_id, redirect_uri, state and code_challenge."""
    verifier, challenge = pkce()
    with TestClient(app) as browser:
        login(browser, "carol", "carol-pass-1")       # created in test_web_origins_cors_and_public_client
        r = browser.get("/oauth/authorize", params={
            "client_id": "spa", "redirect_uri": "http://spa.example.com/", "state": "s",
            "code_challenge": challenge}, follow_redirects=False)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert "code" in q, r.headers["location"]
        plain = browser.get("/oauth/authorize", params={
            "client_id": "spa", "redirect_uri": "http://spa.example.com/", "state": "s",
            "code_challenge": challenge, "code_challenge_method": "plain"}, follow_redirects=False)
        assert parse_qs(urlparse(plain.headers["location"]).query)["error"] == ["invalid_request"]


def test_discovery(client: TestClient):
    doc = client.get("/.well-known/openid-configuration").json()
    assert doc["issuer"] == "http://testserver"
    assert doc["token_endpoint"] == "http://testserver/oauth/token"
