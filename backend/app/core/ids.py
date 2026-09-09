"""UUIDv7 helpers — time-ordered ids keep B-tree indexes local."""

from __future__ import annotations

from uuid import UUID

import uuid_utils


def new_id() -> UUID:
    return UUID(str(uuid_utils.uuid7()))
