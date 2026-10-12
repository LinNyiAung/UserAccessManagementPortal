"""Copy the portal's database to another database (e.g. SQLite -> SQL Server).

    python -m app.migrate_db --to "mssql+pyodbc://@phm\\reportingsvr/AccessManagement?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

Reads from DATABASE_URL (backend/.env, normally sqlite:///./uam.db) unless --from is given.
- Creates the portal's tables in the target (the target database itself must already exist).
- Refuses to run if any of those tables already has rows, so nothing is ever overwritten.
- Copies every table in foreign-key order, keeping the IDs (SQL Server: IDENTITY_INSERT is handled
  by SQLAlchemy), in one transaction: either everything is copied or nothing is.
- Checks the row counts match.
Then point DATABASE_URL at the target and restart the portal. The source database is not changed.
"""

import argparse
import sys

from sqlalchemy import create_engine, func, inspect, select

from . import models  # noqa: F401  (registers the tables)
from .config import settings
from .database import Base, database_url


def _mask(url: str) -> str:
    return database_url(url).render_as_string(hide_password=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--to", required=True, help="target database URL")
    parser.add_argument("--from", dest="source", default=settings.database_url, help="source URL (default: DATABASE_URL)")
    args = parser.parse_args()
    if args.to == args.source:
        sys.exit("Source and target are the same database.")

    # DATABASE_USER / DATABASE_PASSWORD are added to a SQL Server URL that has no user of its own.
    source = create_engine(database_url(args.source))
    target = create_engine(database_url(args.to), pool_pre_ping=True)
    print(f"From: {_mask(args.source)}\nTo:   {_mask(args.to)}")

    tables = Base.metadata.sorted_tables  # parents before children
    missing = [t.name for t in tables if not inspect(source).has_table(t.name)]
    if missing:
        sys.exit(f"Source is missing tables: {', '.join(missing)}")

    Base.metadata.create_all(target)  # creates only tables that don't exist yet
    with target.connect() as conn:
        not_empty = {t.name: n for t in tables if (n := conn.scalar(select(func.count()).select_from(t)))}
    if not_empty:
        sys.exit("Target already has data, nothing copied: "
                 + ", ".join(f"{name} ({n} rows)" for name, n in not_empty.items()))

    counts = {}
    with source.connect() as src, target.begin() as dst:  # one transaction on the target
        for table in tables:
            rows = [dict(r._mapping) for r in src.execute(select(table))]
            if rows:
                dst.execute(table.insert(), rows)
            counts[table.name] = len(rows)
            print(f"  {table.name:<22} {len(rows):>6} rows")

    with target.connect() as conn:
        wrong = {t.name: (counts[t.name], n) for t in tables
                 if (n := conn.scalar(select(func.count()).select_from(t))) != counts[t.name]}
    if wrong:
        sys.exit(f"Row counts differ (source, target): {wrong}")
    print("Done: every table copied and counts match. Now set DATABASE_URL to the target and restart the portal.")


if __name__ == "__main__":
    main()
