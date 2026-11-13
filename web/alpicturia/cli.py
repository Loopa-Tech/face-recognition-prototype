import argparse
import getpass
import json
import os
import time
from .db import Database
from .security import audit, password_hash, uid


def main():
    parser = argparse.ArgumentParser(description="Alpicturia operator commands")
    sub = parser.add_subparsers(dest="command", required=True)
    bootstrap = sub.add_parser(
        "create-admin",
        help="Create an explicitly named administrator; password is read securely.",
    )
    bootstrap.add_argument("--email", required=True)
    bootstrap.add_argument("--name", default="Administration")
    sub.add_parser("doctor", help="Inspect configuration without printing credentials.")
    args = parser.parse_args()
    db = Database()
    if args.command == "doctor":
        import importlib.util

        print(
            json.dumps(
                {
                    "database": str(db.path),
                    "public_base_url": os.getenv(
                        "PUBLIC_BASE_URL", "http://localhost:8000"
                    ),
                    "smtp_configured": bool(
                        os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM")
                    ),
                    "face_engine_installed": bool(
                        importlib.util.find_spec("face_recognition")
                    ),
                    "queued_jobs": db.one(
                        "SELECT count(*) AS n FROM jobs WHERE status='queued'"
                    )["n"],
                },
                indent=2,
            )
        )
        return
    email = args.email.strip().lower()
    if "@" not in email or any(c.isspace() for c in email):
        parser.error("Invalid email")
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        parser.error(
            "Account already exists. No existing account was promoted or modified."
        )
    password = getpass.getpass("Admin password (minimum 12 characters): ")
    if not 12 <= len(password) <= 128:
        parser.error("Password must contain between 12 and 128 characters")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    user_id = uid()
    db.run(
        "INSERT INTO users(id,email,name,password,role,verified,created) VALUES(?,?,?,?,?,?,?)",
        (user_id, email, args.name, password_hash(password), "admin", 1, time.time()),
    )
    audit(db, user_id, "admin.bootstrapped")
    print("Administrator created. Sign in at /account.")


if __name__ == "__main__":
    main()
