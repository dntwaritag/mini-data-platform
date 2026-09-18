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
import time

import requests

logger = logging.getLogger(__name__)

DATABASE_NAME = "Sales Analytics (PostgreSQL)"

WAIT_FOR_HEALTH_TIMEOUT_SECONDS = 180
WAIT_FOR_HEALTH_POLL_INTERVAL_SECONDS = 5


def wait_for_metabase_health(metabase_url: str, timeout: int = WAIT_FOR_HEALTH_TIMEOUT_SECONDS) -> bool:
    """Poll Metabase's own health endpoint until it reports healthy.

    A fresh Metabase instance runs a large Liquibase migration on first boot
    (hundreds of migrations against its H2 app database) and can take well
    over 30 seconds before it answers requests at all. Calling the setup API
    before that finishes gets a connection reset, not a clean error — so
    this wait is not optional; checking docker's health status once and
    moving on is not enough.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{metabase_url}/api/health", timeout=5)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        logger.info("Waiting for Metabase to finish starting...")
        time.sleep(WAIT_FOR_HEALTH_POLL_INTERVAL_SECONDS)
    return False


def login(metabase_url: str, email: str, password: str) -> str:
    resp = requests.post(f"{metabase_url}/api/session", json={"username": email, "password": password}, timeout=15)
    resp.raise_for_status()
    return resp.json()["id"]


def find_database(metabase_url: str, session_id: str, name: str) -> int | None:
    resp = requests.get(f"{metabase_url}/api/database", headers={"X-Metabase-Session": session_id}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    databases = data.get("data", data) if isinstance(data, dict) else data
    for db in databases:
        if db["name"] == name:
            return db["id"]
    return None


def create_database(
    metabase_url: str,
    session_id: str,
    name: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
) -> int:
    payload = {
        "engine": "postgres",
        "name": name,
        "details": {
            "host": db_host,
            "port": db_port,
            "dbname": db_name,
            "user": db_user,
            "password": db_password,
            "ssl": False,
        },
    }
    resp = requests.post(
        f"{metabase_url}/api/database", headers={"X-Metabase-Session": session_id}, json=payload, timeout=30
    )
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_database(
    metabase_url: str,
    session_id: str,
    name: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
) -> int:
    """Guarantee the PostgreSQL data source exists in Metabase, creating it
    if needed. Does not rely on /api/setup having created it — that call
    can report success for the admin-account portion while silently
    dropping the bundled database creation, at least on v0.50.8."""
    existing_id = find_database(metabase_url, session_id, name)
    if existing_id is not None:
        logger.info("Database '%s' already exists (id=%s)", name, existing_id)
        return existing_id

    logger.info("Database '%s' not found — creating it explicitly via /api/database", name)
    db_id = create_database(metabase_url, session_id, name, db_host, db_port, db_name, db_user, db_password)
    logger.info("Created database '%s' (id=%s)", name, db_id)
    return db_id


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
) -> str:
    """Returns 'created', 'already_configured', or 'failed'.

    A truthy setup-token from /api/session/properties does not reliably
    mean setup hasn't happened yet on this version — it can still be
    present after an admin account exists, and /api/setup then rejects the
    call with 403. That case is treated as 'already_configured', not a
    failure: main() falls through to logging in and verifying the database
    directly either way.
    """
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
            "name": DATABASE_NAME,
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
    if resp.status_code == 403 and "currently exists" in resp.text:
        logger.info("Admin account already exists (setup-token was stale) — will verify the database separately.")
        return "already_configured"
    if resp.status_code >= 400:
        logger.error("Metabase setup request failed (%s): %s", resp.status_code, resp.text[:500])
        return "failed"

    logger.info("Metabase admin account created successfully via /api/setup.")
    return "created"


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

    logger.info("Waiting for Metabase to be reachable...")
    if not wait_for_metabase_health(args.metabase_url):
        print(
            f"Metabase did not become healthy within {WAIT_FOR_HEALTH_TIMEOUT_SECONDS}s. "
            "Check `docker compose ps metabase` / `docker compose logs metabase`, "
            "then follow the manual setup steps in dashboards/README.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    token = get_setup_token(args.metabase_url)
    if token:
        result = run_setup(
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
        if result == "failed":
            print(
                "Automated admin setup failed. Follow the manual setup steps "
                "in dashboards/README.md instead.",
                file=sys.stderr,
            )
            sys.exit(1)
        # result is "created" or "already_configured" — either way, fall
        # through to verifying the database below.
    else:
        logger.info("No setup-token available — will verify the database below.")

    # Whether /api/setup ran or not, don't trust it to have reliably created
    # the database (observed: it can report success for the admin account
    # while silently dropping the bundled database creation). Log in and
    # verify/create it explicitly instead.
    try:
        session_id = login(args.metabase_url, args.admin_email, args.admin_password)
    except requests.RequestException as exc:
        print(
            f"Could not log in to verify the database connection: {exc}\n"
            "If the admin account was just created with different credentials than "
            "--admin-email/--admin-password (or METABASE_ADMIN_EMAIL/PASSWORD in .env), "
            "log in manually and add the database via dashboards/README.md instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        ensure_database(
            args.metabase_url,
            session_id,
            DATABASE_NAME,
            args.db_host,
            args.db_port,
            args.db_name,
            args.db_user,
            args.db_password,
        )
    except requests.RequestException as exc:
        body = getattr(exc.response, "text", "")[:500] if getattr(exc, "response", None) is not None else ""
        print(
            f"Could not verify/create the database connection: {exc}\n{body}\n"
            "Follow the manual setup steps in dashboards/README.md instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info("Metabase admin account and PostgreSQL data source are ready.")


if __name__ == "__main__":
    main()
