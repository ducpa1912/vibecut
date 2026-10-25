#!/usr/bin/env python3
"""Local admin bootstrap and password reset CLI."""

from __future__ import annotations

import argparse
import getpass
import sys

import admin.store as store


def _password(prompt: str = "Password: ") -> str:
    first = getpass.getpass(prompt)
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="VibeCut admin account manager")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help="Create the single admin account")
    create.add_argument("--email", required=True)
    create.add_argument("--password", default="")
    reset = sub.add_parser("reset-password", help="Reset the single admin password")
    reset.add_argument("--email", default="")
    reset.add_argument("--password", default="")
    sub.add_parser("show", help="Show whether an admin account exists")
    args = parser.parse_args()

    if args.command == "show":
        user = store.get_user()
        print(user["email"] if user else "no admin account")
        return 0

    if args.command == "create-admin":
        password = args.password or _password("New admin password: ")
        try:
            user = store.create_user(args.email, password)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        store.record_audit("cli", "admin.bootstrap", resource_type="admin", resource_id=user["email"])
        print(f"created admin {user['email']}")
        return 0

    if args.command == "reset-password":
        user = store.get_user(args.email) if args.email else store.get_user()
        if not user:
            print("error: no matching admin account", file=sys.stderr)
            return 1
        password = args.password or _password("New password: ")
        try:
            updated = store.update_user(user["email"], password)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        store.delete_other_sessions(int(updated["id"]))
        store.record_audit("cli", "account.password_reset", resource_type="admin", resource_id=updated["email"])
        print(f"password reset for {updated['email']}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
