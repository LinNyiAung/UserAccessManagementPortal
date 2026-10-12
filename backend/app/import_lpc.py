"""Import the Logistics Price Calculator's users, roles and permissions into the portal.

    python -m app.import_lpc            # dry run: shows what would change, writes nothing
    python -m app.import_lpc --apply    # do it

Reads LPC's own Users and Roles tables (database LogCalculatorTest on phm\\reportingsvr, with the SQL
login from LPC's backend/.env: DWBI_USER / DWBI_PASSWORD) and makes the portal match:
- every permission any LPC role has becomes a permission of the "logistics-calculator" system;
  permissions LPC doesn't have are removed
- every LPC role (except 'system') becomes a portal role granting exactly the same permissions
- every LPC user (except 'system') gets a portal account, keeping their CURRENT LPC password (both use
  bcrypt, so the hash is copied as it is), email <username>@pahtama.com, and their LPC role.
  LPC's 'admin' becomes 'lpc.admin' because 'admin' is the portal's own administrator.
  Existing portal accounts are matched by username and keep their portal password.
- portal users who hold an LPC role but aren't LPC users lose that role.
Safe to re-run. Everything goes through one transaction and is written to the portal's audit log.
After this, manage LPC's users and roles in the portal; LPC's own tables are not changed.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL

from .database import SessionLocal
from .models import Application, AuditLog, Permission, Role, User

CLIENT_ID = "logistics-calculator"
DEFAULT_LPC_ENV = r"C:\projects\LogisticsPriceCalculator\backend\.env"


def _read_env(path: str) -> dict:
    values = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _describe(permission: str) -> str:
    """'view_rate_carts' -> 'View rate carts'."""
    return permission.replace("_", " ").capitalize()


def read_lpc(url) -> tuple[dict, list]:
    with create_engine(url).connect() as conn:
        roles = {name: (json.loads(perms) if perms else [])
                 for name, perms in conn.execute(text("SELECT name, permissions FROM Roles"))}
        users = [dict(r._mapping) for r in conn.execute(
            text("SELECT id, username, hashed_password, role FROM Users ORDER BY id"))]
    return roles, users


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--lpc-url", help="LPC database URL (default: built from --lpc-env)")
    parser.add_argument("--lpc-env", default=DEFAULT_LPC_ENV, help="LPC's backend/.env with DWBI_USER / DWBI_PASSWORD")
    parser.add_argument("--lpc-server", default="phm\\reportingsvr")
    parser.add_argument("--lpc-database", default="LogCalculatorTest")
    parser.add_argument("--email-domain", default="pahtama.com")
    parser.add_argument("--skip", default="system", help="LPC users and roles not to import (comma-separated)")
    parser.add_argument("--rename", default="admin=lpc.admin", help="LPC username=portal username pairs")
    args = parser.parse_args()

    if args.lpc_url:
        lpc_url = args.lpc_url
    else:
        env = _read_env(args.lpc_env)
        lpc_url = URL.create(
            "mssql+pyodbc", username=env["DWBI_USER"], password=env["DWBI_PASSWORD"],
            host=args.lpc_server, database=args.lpc_database,
            query={"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"},
        )
    skip = {x.strip().lower() for x in args.skip.split(",") if x.strip()}
    rename = {a.strip().lower(): b.strip() for a, b in (p.split("=", 1) for p in args.rename.split(",") if "=" in p)}

    lpc_roles, lpc_users = read_lpc(lpc_url)
    lpc_roles = {n: p for n, p in lpc_roles.items() if n.lower() not in skip}
    lpc_users = [u for u in lpc_users if u["username"].lower() not in skip]
    print(f"LPC: {len(lpc_roles)} roles, {len(lpc_users)} users (skipping: {', '.join(sorted(skip)) or 'none'})")

    with SessionLocal() as db:
        app = db.scalar(select(Application).where(Application.client_id == CLIENT_ID))
        if app is None:
            sys.exit(f"The portal has no system with client ID '{CLIENT_ID}'. Register LPC in the portal first.")
        log = []

        def audit(action: str, target: str, detail: str = ""):
            log.append(f"  {action:<20} {target}{'  ' + detail if detail else ''}")
            db.add(AuditLog(actor_username="import_lpc", action=action, target=target, detail=detail, ip="script"))

        # -- permissions --------------------------------------------------------------------------
        wanted = sorted({p for perms in lpc_roles.values() for p in perms})
        perms = {p.name.lower(): p for p in app.permissions}
        for name in wanted:
            if name.lower() not in perms:
                perms[name.lower()] = Permission(application=app, name=name, description=_describe(name))
                db.add(perms[name.lower()])  # SQLAlchemy 2.0 doesn't add objects through the back-reference
                audit("permission.create", f"{app.name}:{name}")
        for key, p in list(perms.items()):
            if key not in {w.lower() for w in wanted}:
                audit("permission.delete", f"{app.name}:{p.name}", "not an LPC permission")
                db.delete(p)
                del perms[key]

        # -- roles ----------------------------------------------------------------------------------
        roles = {r.name.lower(): r for r in app.roles}
        for name, role_perms in sorted(lpc_roles.items()):
            role = roles.get(name.lower())
            if role is None:
                role = roles[name.lower()] = Role(application=app, name=name, description=f"LPC role '{name}'")
                db.add(role)
                audit("role.create", f"{app.name}:{name}")
            elif role.name != name:
                audit("role.update", f"{app.name}:{role.name}", f"renamed to {name}")
                role.name = name
            new = sorted({perms[p.lower()].name for p in role_perms if p.lower() in perms})
            if sorted(p.name for p in role.permissions) != new:
                role.permissions = [perms[p.lower()] for p in new]
                audit("role.permissions", f"{app.name}:{name}", f"{len(new)} permissions")
        for key, role in list(roles.items()):
            if key not in {n.lower() for n in lpc_roles}:
                audit("role.delete", f"{app.name}:{role.name}", "not an LPC role")
                db.delete(role)
                del roles[key]
        db.flush()

        # -- users ----------------------------------------------------------------------------------
        imported, warnings = set(), []
        for u in lpc_users:
            username = rename.get(u["username"].lower(), u["username"]).strip()
            email = f"{username.lower()}@{args.email_domain}"
            user = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
            if user is None:
                if db.scalar(select(User).where(func.lower(User.email) == email)):
                    audit("user.skipped", username, f"email {email} already belongs to another portal user")
                    continue
                user = User(username=username, email=email, full_name=username,
                            password_hash=u["hashed_password"], is_active=True)
                db.add(user)
                audit("user.create", username, f"LPC user {u['username']} (id {u['id']}), LPC password kept")
            imported.add(username.lower())
            role = roles.get((u["role"] or "").lower())
            if role is None:
                warnings.append(f"  {username}: LPC role '{u['role']}' isn't in LPC's Roles table, so no LPC access "
                                "(same as in LPC today). Give them a role in the portal if they need it.")
            current = {r for r in user.roles if r.application_id == app.id}
            wanted_roles = {role} if role else set()
            if current != wanted_roles:
                user.roles = [r for r in user.roles if r.application_id != app.id] + list(wanted_roles)
                audit("user.roles", username, f"{app.name}: {role.name if role else 'NONE'}"
                      + ("" if role else f" (LPC role '{u['role']}' doesn't exist in LPC's Roles table)"))

        # -- portal users holding an LPC role who aren't LPC users ------------------------------------
        for role in roles.values():
            for member in list(role.users):
                if member.username.lower() not in imported:
                    role.users.remove(member)
                    audit("user.roles", member.username, f"{app.name}: removed {role.name} (not an LPC user)")

        print(f"{'Changes' if args.apply else 'Dry run - would change'} ({len(log)}):")
        print("\n".join(log) if log else "  nothing, the portal already matches LPC")
        if warnings:
            print("Check:\n" + "\n".join(warnings))
        if args.apply:
            db.commit()
            print("Done. Manage LPC's users and roles in the portal from now on.")
        else:
            db.rollback()
            print("Nothing written. Run again with --apply to make these changes.")


if __name__ == "__main__":
    main()
