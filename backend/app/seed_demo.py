"""Register the systems with their roles and permissions, and give the admin a role in each.

    python -m app.seed_demo

Currently: the Promotion Approval Form. (The Logistics Price Calculator was registered in the portal UI.)
Re-running is safe: roles and permissions that already exist are left alone, so edits made in the portal
are kept. Server-side systems (with a client secret) get their credentials written to an env file in
examples/demo_client/; browser apps like PAF have no secret.
"""

from pathlib import Path

from sqlalchemy import select

from .config import settings
from .database import SessionLocal, create_schema
from .models import Application, Permission, Role, User
from .security import hash_token, new_token

DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "demo_client"

SYSTEMS = [
    {
        # C:\projects\PromotionApprovalForm: React app (oidc-client-ts) + FastAPI API that checks permissions.
        # Runs on Vite (5180) in development or served by its API (8200), so both addresses are registered.
        "name": "Promotion Approval Form",
        "client_id": "promotion-approval",
        "urls": ["http://localhost:5180", "http://localhost:8200"],
        "public": True,
        "description": "Trade promotion set-up and DOA approvals.",
        "roles": {
            "requester": "Raises promotion set-ups",
            "approver": "Approves in the DOA chain (the approver profile with the user's email)",
        },
        "permissions": {
            "promotions.create": ("Raise promotion set-ups: drafts, attachments, final submit, and see own submissions",
                                  ["requester"]),
            "promotions.approve": ("Approve or reject promotions routed to the user's approver profile "
                                   "(matched by email)", ["approver"]),
            "reports.view": ("See the dashboard (totals for all submitted promotions)", ["requester", "approver"]),
            "reports.export": ("Export all promotions as CSV", ["requester", "approver"]),
        },
        "admin_role": ["requester", "approver"],
    },
]


def set_env_line(path: Path, key: str, value: str) -> None:
    """Set KEY=value in an env file, keeping every other line (including the secret)."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    lines = [line for line in lines if not line.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def register(db, admin: User | None, spec: dict) -> None:
    urls = spec.get("urls") or [f"http://localhost:{spec['port']}"]
    base_url = urls[0]
    public = spec.get("public", False)

    app = db.scalar(select(Application).where(Application.client_id == spec["client_id"]))
    if app is None:
        app = Application(
            name=spec["name"],
            client_id=spec["client_id"],
            description=spec["description"],
            home_url=f"{base_url}/",
            # Browser apps (the React kit) come back to the app's root; server apps to /callback.
            redirect_uris=[f"{url}/" if public else f"{url}/callback" for url in urls],
            web_origins=urls if public else [],
        )
        db.add(app)

    existing_roles = {r.name for r in app.roles}
    for name, description in spec["roles"].items():
        if name not in existing_roles:
            app.roles.append(Role(name=name, description=description))
    roles = {r.name: r for r in app.roles}

    existing_perms = {p.name for p in app.permissions}
    for name, (description, granted_by) in spec["permissions"].items():
        if name in existing_perms:
            continue
        permission = Permission(name=name, description=description)
        app.permissions.append(permission)
        for role_name in granted_by:
            roles[role_name].permissions.append(permission)

    if admin:
        admin_roles = spec["admin_role"] if isinstance(spec["admin_role"], list) else [spec["admin_role"]]
        for name in admin_roles:
            if roles[name] not in admin.roles:
                admin.roles.append(roles[name])

    if public:
        print(f"{spec['name']}: registered as a browser app (no secret; web origins {', '.join(urls)})")
        return

    env_path = DEMO_DIR / spec["env_file"]
    if env_path.exists() and app.client_secret_hash:
        set_env_line(env_path, "APP_NAME", spec["name"])
        set_env_line(env_path, "APP_URL", f"{base_url}/")
        set_env_line(env_path, "PAGES", spec["pages"])
        print(f"{spec['name']}: up to date (secret in {env_path.name} kept, page rules updated)")
        return
    secret = new_token()
    app.client_secret_hash = hash_token(secret)
    env_path.write_text(
        f"APP_NAME={spec['name']}\n"
        f"APP_URL={base_url}/\n"
        f"PAGES={spec['pages']}\n"
        f"SSO_ISSUER={settings.issuer}\n"
        f"SSO_CLIENT_ID={spec['client_id']}\n"
        f"SSO_CLIENT_SECRET={secret}\n"
        f"SSO_REDIRECT_URI={base_url}/callback\n"
        f"SESSION_SECRET={new_token()}\n"
    )
    print(f"{spec['name']}: registered, client credentials written to {env_path}")


def main() -> None:
    create_schema()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == settings.admin_username))
        for spec in SYSTEMS:
            register(db, admin, spec)
        db.commit()


if __name__ == "__main__":
    main()
