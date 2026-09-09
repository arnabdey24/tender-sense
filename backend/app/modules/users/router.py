"""The signed-in user's own account.

Password changes live under ``/auth/change-password`` because they rotate the
session; everything here is plain profile data.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.auth.schemas import UserRead
from app.modules.users.schemas import UserUpdate

router = APIRouter(tags=["users"])


@router.patch("/users/me", response_model=UserRead, summary="Update your profile")
async def update_me(data: UserUpdate, user: CurrentUser, db: DbSession) -> UserRead:
    """Change your display name or avatar.

    The email address is not editable here: moving an account to a new address
    has to re-run verification.
    """
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    return UserRead.model_validate(user)
