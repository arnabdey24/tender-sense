"""The script that grants platform staff.

It is the only supported way to make an operator, so what it must not do
matters as much as what it does: promoting somebody's working account is not
licence to reset the password they are still using.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.security import hash_password, verify_password
from app.db.session import session_scope
from app.modules.notifications.models import EmailOutbox
from app.modules.users.models import User
from scripts.create_superuser import create_superuser, generate_password


@pytest.fixture
async def address() -> AsyncIterator[str]:
    email = f"ops-{uuid4().hex[:12]}@tsense-test.io"
    yield email
    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        found = await session.scalar(select(User).where(User.email == email))
        if found is not None:
            await session.delete(found)


async def load(email: str) -> User | None:
    async with session_scope() as session:
        return await session.scalar(select(User).where(User.email == email))


class TestCreating:
    async def test_a_new_operator_can_sign_in_immediately(self, address: str) -> None:
        """No inbox round trip: the operator running this is the verification,
        and on a fresh deployment the mail may not be configured yet."""
        _, password = await create_superuser(
            address, full_name="Ops", password=None, reset_password=False
        )

        user = await load(address)
        assert user is not None
        assert user.is_superuser is True
        assert user.is_active is True
        assert user.email_verified is True
        assert password is not None
        assert verify_password(password, user.password_hash)

    async def test_the_address_is_normalised(self, address: str) -> None:
        await create_superuser(
            f"  {address.upper()}  ", full_name=None, password=None, reset_password=False
        )

        assert await load(address) is not None

    async def test_something_that_is_not_an_address_is_refused(self) -> None:
        with pytest.raises(SystemExit):
            await create_superuser(
                "not-an-address", full_name=None, password=None, reset_password=False
            )


class TestPromoting:
    async def test_promoting_leaves_the_password_alone(self, address: str) -> None:
        """The sharp edge. Someone granting staff to a colleague must not
        silently lock them out of the account they are signed in to."""
        async with session_scope() as session:
            session.add(
                User(
                    email=address,
                    full_name="Existing Person",
                    password_hash=hash_password("the-password-they-already-use"),
                )
            )

        _, issued = await create_superuser(
            address, full_name=None, password=None, reset_password=False
        )

        user = await load(address)
        assert user is not None
        assert user.is_superuser is True
        assert issued is None
        assert verify_password("the-password-they-already-use", user.password_hash)

    async def test_a_reset_is_only_done_when_asked_for(self, address: str) -> None:
        async with session_scope() as session:
            session.add(
                User(
                    email=address,
                    full_name="Existing Person",
                    password_hash=hash_password("the-password-they-already-use"),
                )
            )

        _, issued = await create_superuser(
            address, full_name=None, password=None, reset_password=True
        )

        user = await load(address)
        assert issued is not None
        assert user is not None
        assert verify_password(issued, user.password_hash)

    async def test_a_suspended_operator_is_restored(self, address: str) -> None:
        """Otherwise granting staff to a suspended account produces a staff
        member who still cannot sign in, and says it worked."""
        async with session_scope() as session:
            session.add(
                User(
                    email=address,
                    full_name="Suspended Person",
                    password_hash=hash_password("a-perfectly-fine-password"),
                    is_active=False,
                )
            )

        await create_superuser(address, full_name=None, password=None, reset_password=False)

        user = await load(address)
        assert user is not None
        assert user.is_active is True
        assert user.is_superuser is True


class TestGeneratedPasswords:
    async def test_they_are_long_and_unambiguous_to_read_out(self) -> None:
        """These get read down a phone or copied out of a terminal, so the
        characters that look like each other are not in the alphabet."""
        password = generate_password()

        assert len(password) == 24
        assert not set(password) & set("0O1lI")
        assert generate_password() != password
