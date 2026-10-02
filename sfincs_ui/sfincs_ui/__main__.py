"""``python -m sfincs_ui``: migrate, create-admin, preflight, serve."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys

import uvicorn

from sfincs_ui.config import get_config
from sfincs_ui.services.environment import check_environment

MIN_PASSWORD_LEN = 8


def _cmd_migrate(_args) -> int:
    from sqlalchemy import text

    from sfincs_ui.db import base

    base.init_db()
    with base.get_engine().connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"database at {get_config().database_url_resolved} is at revision {version}")
    return 0


def _read_password() -> str | None:
    env = os.environ.get("SFINCS_UI_ADMIN_PASSWORD")
    if env is not None:
        if len(env) < MIN_PASSWORD_LEN:
            print(f"error: password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
            return None
        return env
    first = getpass.getpass("Admin password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("error: passwords do not match", file=sys.stderr)
        return None
    if len(first) < MIN_PASSWORD_LEN:
        print(f"error: password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
        return None
    return first


def _cmd_create_admin(args) -> int:
    from sfincs_ui.db import base
    from sfincs_ui.services.auth_service import AuthService

    base.init_db()
    auth = AuthService()
    existing = [u for u in auth.list_users() if u["role"] == "admin"]
    if existing:
        print(f"admin '{existing[0]['username']}' already exists; nothing changed")
        return 0
    password = _read_password()
    if password is None:
        return 2
    user, created = auth.ensure_admin(args.username, password, email=args.email)
    print(f"created admin '{user['username']}'" if created else f"admin '{user['username']}' already exists")
    return 0


def _cmd_preflight(_args) -> int:
    report = check_environment(get_config(), deep=True)
    if report.ok:
        print("preflight OK")
        return 0
    for p in report.problems:
        print(f"preflight: {p}", file=sys.stderr)
    return 1


def _cmd_serve(args) -> int:
    cfg = get_config()
    uvicorn.run(
        "sfincs_ui.asgi:app",
        host=args.host,
        port=args.port or cfg.port,
        root_path=cfg.url_prefix,
        reload=args.reload,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m sfincs_ui", description="SFINCS UI maintenance commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the database schema").set_defaults(func=_cmd_migrate)
    p = sub.add_parser("create-admin", help="create the first admin account (no-op when one exists)")
    p.add_argument("--username", default="admin")
    p.add_argument("--email", default=None)
    p.set_defaults(func=_cmd_create_admin)
    sub.add_parser("preflight", help="verify binary, model env, inputs and workspace").set_defaults(func=_cmd_preflight)
    p = sub.add_parser("serve", help="run the app with uvicorn")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=_cmd_serve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
