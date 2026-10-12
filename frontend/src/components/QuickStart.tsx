import { useState, type ReactNode } from "react";
import type { Application } from "../api";
import Icon from "./Icon";
import { CopyButton, Tabs } from "./ui";

type Pattern = "react" | "api" | "server";

function CodeBlock({ title, code }: { title: string; code: string }) {
  return (
    <div className="code-block">
      <div className="code-block-head">
        <span>{title}</span>
        <CopyButton value={code} label={`Copy ${title}`} />
      </div>
      <pre>{code}</pre>
    </div>
  );
}

function download(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

function Check({ ok, optional, children }: { ok: boolean; optional?: boolean; children: ReactNode }) {
  return (
    <li className={ok ? "ok" : optional ? "optional" : "todo"}>
      <Icon name={ok ? "check" : "alert"} size={15} />
      <span>{children}</span>
    </li>
  );
}

export default function QuickStart({ app, portal }: { app: Application; portal: string }) {
  const [pattern, setPattern] = useState<Pattern>(app.is_confidential ? "server" : "react");
  const examplePerm = app.permissions[0]?.name ?? "example.view";
  const redirect = app.redirect_uris[0] ?? (app.is_confidential ? "https://your-app/auth/callback" : "https://your-app/");

  const exampleRole = app.roles[0]?.name ?? "user";
  const reactEnv = `VITE_PORTAL_URL=${portal}\nVITE_PORTAL_CLIENT_ID=${app.client_id}\n`;
  const apiEnv =
    `PORTAL_ISSUER=${portal}\nPORTAL_CLIENT_ID=${app.client_id}\nPORTAL_PUBLIC_KEY_FILE=./portal_public_key.pem\n`;
  const serverEnv =
    `SSO_ISSUER=${portal}\nSSO_CLIENT_ID=${app.client_id}\n` +
    `SSO_CLIENT_SECRET=<the secret shown when the system was registered or the secret was rotated>\n` +
    `SSO_REDIRECT_URI=${redirect}\n`;

  return (
    <div className="card quick-start">
      <h2>Quick start</h2>
      <p className="muted small">Ready-made setup for {app.name}, with its values filled in. Pick how the system is built.</p>

      <ul className="readiness">
        <Check ok={app.redirect_uris.length > 0}>Redirect URI registered</Check>
        {!app.is_confidential && <Check ok={app.web_origins.length > 0}>Web origins set (Settings tab), so the browser may call the portal</Check>}
        <Check ok={app.roles.length > 0}>Roles defined (Roles tab)</Check>
        <Check ok={app.permissions.length > 0} optional>Permissions defined (Permissions tab), so code can check them</Check>
        <Check ok={app.member_count > 0}>At least one user has access (a user's page → System access)</Check>
      </ul>

      <Tabs<Pattern>
        value={pattern}
        onChange={setPattern}
        tabs={[
          { id: "react", label: "React app" },
          { id: "api", label: "Python API (FastAPI)" },
          { id: "server", label: "Server-side web app" },
        ]}
      />

      {pattern === "react" && (
        <>
          {app.is_confidential && (
            <div className="alert info small-alert">
              <Icon name="alert" /> React apps must be registered as <b>Browser or mobile app</b> (no secret). Register a separate
              system for the React app, or change this one.
            </div>
          )}
          <p className="small">
            Uses the standard OpenID Connect library <code>oidc-client-ts</code> (with <code>react-oidc-context</code>). It handles
            the redirect, state + PKCE, swapping the code for tokens, refreshing them and signing out. Your app decides when
            sign-in is needed and sends the access token to its API. Pair it with the Python API tab for the backend.
          </p>
          <CodeBlock title="1. Install" code={"npm install oidc-client-ts react-oidc-context"} />
          <CodeBlock title="2. Settings (.env)" code={reactEnv} />
          <CodeBlock
            title="3. Configure the library (src/auth.js)"
            code={`import { UserManager } from 'oidc-client-ts'

const HOME = \`\${window.location.origin}/\`        // must be a registered redirect URI

export const userManager = new UserManager({
  authority: import.meta.env.VITE_PORTAL_URL,      // reads /.well-known/openid-configuration
  client_id: import.meta.env.VITE_PORTAL_CLIENT_ID,
  redirect_uri: HOME,                              // the portal sends ?code= back here
  post_logout_redirect_uri: HOME,                  // and comes back here after sign-out
  scope: 'openid profile email',
  automaticSilentRenew: true,                      // refresh tokens before they expire
})

export const signIn = () => userManager.signinRedirect()
// Pass useAuth()'s object, not userManager: the hook marks the redirect as in progress, so the
// "nobody signed in → sign in" effect doesn't race the sign-out and sign the user straight back in.
export const signOut = (auth) => auth.signoutRedirect({ client_id: import.meta.env.VITE_PORTAL_CLIENT_ID })
// after the code swap: remove ?code=&state= from the address bar
export const onSigninCallback = () => window.history.replaceState(null, '', '/')

export async function getAccessToken() {
  const user = await userManager.getUser()
  return user && !user.expired ? user.access_token : null
}`}
          />
          <CodeBlock
            title="4. Wrap the app (main.jsx)"
            code={`import { AuthProvider } from 'react-oidc-context'
import { userManager, onSigninCallback } from './auth'

// Handles the return from the portal (?code=), stores and refreshes the tokens,
// and shares the sign-in state with every component through useAuth().
<AuthProvider userManager={userManager} onSigninCallback={onSigninCallback}>
  <App />
</AuthProvider>`}
          />
          <CodeBlock
            title="5. Sign in when nobody is signed in (App.jsx)"
            code={`import { useEffect } from 'react'
import { hasAuthParams, useAuth } from 'react-oidc-context'
import { signIn, signOut } from './auth'

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    // not loading, nobody signed in, no redirect running, no error, not the portal's reply
    if (!auth.isLoading && !auth.isAuthenticated && !auth.activeNavigator && !auth.error && !hasAuthParams()) signIn()
  }, [auth.isLoading, auth.isAuthenticated, auth.activeNavigator, auth.error])

  if (auth.error) return <p>{auth.error.message}</p>        // e.g. no access to this system
  if (!auth.isAuthenticated) return <p>Signing you in…</p>

  return (
    <>
      Hello {auth.user.profile.name}
      <button onClick={() => signOut(auth)}>Sign out</button>
    </>
  )
}`}
          />
          <CodeBlock
            title="6. Send the token with every API call"
            code={`import { getAccessToken, signIn } from './auth'

export async function api(path, options = {}) {
  const token = await getAccessToken()
  if (!token) return signIn()
  const res = await fetch(path, { ...options, headers: { ...options.headers, Authorization: \`Bearer \${token}\` } })
  if (res.status === 401) return signIn()          // token rejected → sign in again
  return res.json()
}`}
          />
          <p className="muted small">
            The token's <code>roles</code> and <code>permissions</code> are in <code>auth.user.profile</code> for showing or
            hiding UI, but the API must check them itself. The app's redirect URI should be its root address
            (e.g. <code>{redirect}</code>), and that address must be in Web origins.
          </p>
          <button className="btn small" onClick={() => download(".env", reactEnv)}><Icon name="external" size={14} /> Download .env</button>
        </>
      )}

      {pattern === "api" && (
        <>
          <p className="small">
            Checks the access token the frontend sends with every request, locally with the portal's public key (no call to
            the portal), then checks the user's roles or permissions for each endpoint.
          </p>
          <div className="code-block">
            <div className="code-block-head"><span>1. Save the portal's public key in the backend folder</span></div>
            <div className="code-block-body">
              <p className="small">
                It can only check the portal's signatures, never create them, so it isn't secret. Replace it if the portal
                ever changes its signing key.
              </p>
              <a className="btn small" href={`${portal}/oauth/public-key.pem`} download="portal_public_key.pem">
                <Icon name="external" size={14} /> Download portal_public_key.pem
              </a>
            </div>
          </div>
          <CodeBlock title="2. Install" code={"pip install pyjwt cryptography"} />
          <CodeBlock title="3. Settings (.env)" code={apiEnv} />
          <CodeBlock
            title="4. Check the token (auth.py)"
            code={`import os
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

bearer = HTTPBearer(auto_error=False)        # reads "Authorization: Bearer <token>"

@lru_cache
def public_key() -> str:
    return open(os.environ["PORTAL_PUBLIC_KEY_FILE"]).read()

def current_user(cred = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "Sign in first")
    try:
        # signature (not forged or edited), issuer (our portal), audience (this system), expiry
        return jwt.decode(cred.credentials, public_key(), algorithms=["RS256"],
                          issuer=os.environ["PORTAL_ISSUER"], audience=os.environ["PORTAL_CLIENT_ID"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired sign-in token")

def require_role(role: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if role not in user.get("roles", []):
            raise HTTPException(403, f"Requires the '{role}' role")
        return user
    return check

def require_permission(permission: str):
    def check(user: dict = Depends(current_user)) -> dict:
        if permission not in user.get("permissions", []):
            raise HTTPException(403, f"Requires the '{permission}' permission")
        return user
    return check`}
          />
          <CodeBlock
            title="5. Protect endpoints"
            code={`from fastapi import Depends
from .auth import current_user, require_permission, require_role

@app.get("/api/me")                                    # anyone with access to this system
def me(user: dict = Depends(current_user)):
    return {"name": user["name"], "roles": user["roles"], "permissions": user["permissions"]}

@app.get("/api/things")                                # only users with this permission
def things(user: dict = Depends(require_permission("${examplePerm}"))):
    ...

@app.post("/api/approve")                              # only users with this role
def approve(user: dict = Depends(require_role("${exampleRole}"))):
    ...`}
          />
          <p className="muted small">
            The token carries <code>sub</code> (permanent user ID), <code>preferred_username</code>, <code>name</code>,
            <code> email</code>, <code>roles</code> and <code>permissions</code> for this system. Keep your own user records keyed
            by <code>sub</code> if you need them; always take the user's identity from the token, never from the request body.
          </p>
          <button className="btn small" onClick={() => download(".env", apiEnv)}><Icon name="external" size={14} /> Download .env</button>
        </>
      )}

      {pattern === "server" && (
        <>
          {!app.is_confidential && (
            <div className="alert info small-alert">
              <Icon name="alert" /> Server-side apps should be registered as <b>Server-side app</b>, so they get a client secret.
            </div>
          )}
          <p className="small">
            For apps that render pages on the server (ASP.NET, Spring, Django, Laravel, Express…). Use the framework's standard
            OpenID Connect library with these values:
          </p>
          <CodeBlock title=".env" code={serverEnv} />
          <ul className="small lib-list">
            <li><b>.NET:</b> <code>Microsoft.AspNetCore.Authentication.OpenIdConnect</code> (Authority = issuer)</li>
            <li><b>Java:</b> <code>spring-boot-starter-oauth2-client</code> (issuer-uri = issuer)</li>
            <li><b>Python:</b> <code>authlib</code> (server_metadata_url = issuer + /.well-known/openid-configuration)</li>
            <li><b>Node:</b> <code>openid-client</code> or Auth.js</li>
            <li><b>PHP:</b> <code>jumbojett/openid-connect-php</code></li>
          </ul>
          <p className="muted small">Scopes <code>openid profile email</code>; read the <code>roles</code> and <code>permissions</code> claims from the ID token.</p>
          <button className="btn small" onClick={() => download(".env", serverEnv)}><Icon name="external" size={14} /> Download .env</button>
        </>
      )}
    </div>
  );
}
