"""Best-effort automated Metabase setup.

Metabase exposes a one-shot `/api/setup` endpoint that is only usable on a
completely fresh instance (before any admin account exists) and requires a
`setup_token` that Metabase prints in its own startup logs. This script
attempts that automated path — creating the admin user and registering the
PostgreSQL analytics database as a data source in a single call — and exits
cleanly with next-step instructions if that's not possible (e.g. Metabase
has already been set up, or the setup token can't be discovered).

This automation is intentionally best-effort: Metabase's setup flow varies
across versions and isn't guaranteed to be stable across upgrades. If it
fails, follow the manual steps in dashboards/README.md — they always work
and are the documented source of truth.

Usage:
    python scripts/init_metabase.py --metabase-url http://localhost:3000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)


def get_setup_token(metabase_url: str) -> str | None:
    """Metabase's /api/session/properties exposes `setup-token` while the
    instance has not yet been set up. Returns None once setup is complete."""
    try:
        resp = requests.get(f"{metabase_url}/api/session/properties", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not reach Metabase at %s: %s", metabase_url, exc)
        return None

    token = data.get("setup-token")
    if not token:
        logger.info("No setup-token available — Metabase is likely already configured.")
    return token


def run_setup(
    metabase_url: str,
    setup_token: str,
    admin_email: str,
    admin_password: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
) -> bool:
    payload = {
        "token": setup_token,
        "user": {
            "first_name": "Admin",
            "last_name": "User",
            "email": admin_email,
            "password": admin_password,
            "site_name": "Mini Data Platform",
        },
        "database": {
            "engine": "postgres",
            "name": "Sales Analytics (PostgreSQL)",
            "details": {
                "host": db_host,
                "port": db_port,
                "dbname": db_name,
                "user": db_user,
                "password": db_password,
                "ssl": False,
            },
        },
        "prefs": {"site_name": "Mini Data Platform", "allow_tracking": False},
    }

    resp = requests.post(f"{metabase_url}/api/setup", json=payload, timeout=30)
    if resp.status_code >= 400:
        logger.error("Metabase setup request failed (%s): %s", resp.status_code, resp.text[:500])
        return False

    logger.info("Metabase admin account and PostgreSQL data source created successfully.")
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Best-effort automated Metabase setup.")
    parser.add_argument("--metabase-url", default=os.environ.get("METABASE_URL", "http://localhost:3000"))
    parser.add_argument("--admin-email", default=os.environ.get("METABASE_ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--admin-password", default=os.environ.get("METABASE_ADMIN_PASSWORD", "ChangeMe123!"))
    parser.add_argument("--db-host", default=os.environ.get("ANALYTICS_DB_HOST", "postgres"))
    parser.add_argument("--db-port", type=int, default=int(os.environ.get("ANALYTICS_DB_PORT", "5432")))
    parser.add_argument("--db-name", default=os.environ.get("ANALYTICS_DB_NAME", "mini_data_platform"))
    parser.add_argument("--db-user", default=os.environ.get("ANALYTICS_DB_USER", "platform_user"))
    parser.add_argument("--db-password", default=os.environ.get("ANALYTICS_DB_PASSWORD", "platform_pass"))
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    token = get_setup_token(args.metabase_url)
    if not token:
        print(
            "Automated setup is not available (Metabase unreachable or already configured).\n"
            "Follow the manual setup steps in dashboards/README.md instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    ok = run_setup(
        args.metabase_url,
        token,
        args.admin_email,
        args.admin_password,
        args.db_host,
        args.db_port,
        args.db_name,
        args.db_user,
        args.db_password,
    )
    if not ok:
        print(
            "Automated setup failed. Follow the manual setup steps in dashboards/README.md instead.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
