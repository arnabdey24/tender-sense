"""Create a platform operator, or promote an existing account to one.

Platform staff — the people who reach `/admin`, register portals, move rate
limits and suspend accounts — could previously only be made with an UPDATE
statement against the users table. That is a poor answer to a routine question,
and a worse one at three in the morning: it needs database access, it silently
does nothing if the email is misspelled, and there is no record of what it did.

Two jobs, on purpose:

* an email nobody holds yet is created, verified, and given a password;
* an email that already exists is promoted, and its password is left alone
  unless you explicitly ask for a new one. Somebody's working account is not
  something a staff-grant command should quietly reset.

Usage:

    uv run python -m scripts.create_superuser --email ops@example.com
    uv run python -m scripts.create_superuser --email ops@example.com --password '...'
    uv run python -m scripts.create_superuser --email ops@example.com --reset-password

Through the stack, where the database lives:

    docker compose run --rm api python -m scripts.create_superuser --email ops@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import string
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import dispose_engine, session_scope
from app.modules.users.models import User

#: Unambiguous in a terminal and when read aloud down a phone: no 0/O, no 1/l/I.
ALPHABET = (string.ascii_lowercase + string.ascii_uppercase + string.digits).translate(
    str.maketrans("", "", "0O1lI")
)


def generate_password(length: int = 24) -> str:
    """A password nobody has to invent, and nobody will reuse.

    Generated rather than prompted because an operator asked to think one up at
    the moment of creating an account reliably thinks up a memorable one.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def create_superuser(
    email: str, *, full_name: str | None, password: str | None, reset_password: bool
) -> tuple[str, str | None]:
    """Returns what happened, and the password if this run set one."""
    address = email.strip().lower()
    if not address or "@" not in address:
        raise SystemExit(f"'{email}' is not an email address.")

    async with session_scope() as session:
        existing = await session.scalar(select(User).where(User.email == address))

        if existing is not None:
            changed = []
            if not existing.is_superuser:
                existing.is_superuser = True
                changed.append("granted platform staff")
            if not existing.is_active:
                existing.is_active = True
                changed.append("reactivated")
            if existing.email_verified_at is None:
                existing.email_verified_at = utcnow()
                changed.append("marked verified")

            issued: str | None = None
            if password or reset_password:
                issued = password or generate_password()
                existing.password_hash = hash_password(issued)
                changed.append("set a new password")

            await session.flush()
            return (
                f"{address}: {', '.join(changed)}." if changed else f"{address}: already staff.",
                issued,
            )

        issued = password or generate_password()
        session.add(
            User(
                email=address,
                full_name=full_name or address.split("@")[0],
                password_hash=hash_password(issued),
                # An operator creating this account is the verification; there is
                # no inbox round trip to wait for, and on a fresh deployment the
                # mail may not be configured yet.
                email_verified_at=utcnow(),
                is_superuser=True,
                is_active=True,
            )
        )
        await session.flush()
        return f"{address}: created as platform staff.", issued


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Address that will sign in")
    parser.add_argument("--name", default=None, help="Full name; defaults to the local part")
    parser.add_argument(
        "--password",
        default=None,
        help="Set this password. Omit to have one generated and printed once.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Generate a new password for an account that already exists.",
    )
    args = parser.parse_args()

    if args.password and len(args.password) < settings.password_min_length:
        raise SystemExit(
            f"That password is shorter than the {settings.password_min_length} characters "
            "this deployment requires, and the account would be unable to change it later."
        )

    configure_logging()
    try:
        summary, issued = await create_superuser(
            args.email,
            full_name=args.name,
            password=args.password,
            reset_password=args.reset_password,
        )
    finally:
        await dispose_engine()

    print(summary)
    if issued and not args.password:
        # Printed once, never stored anywhere this script can reach.
        print(f"password: {issued}")
        print("Store it now — it is not recoverable, and change it after signing in.")
    elif issued:
        print("password: the one you supplied.")

    print(f"Sign in at {settings.app_url.rstrip('/')}/login, then open /admin.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        sys.exit(130)
