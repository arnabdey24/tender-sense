"""Unit-level checks for the admin service that need no database."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.modules.admin.service import _check_adapter


class TestAdapterValidation:
    @pytest.mark.parametrize("adapter_key", ["manual", "worldbank", "egp_bd", "egp_bd_playwright"])
    def test_planned_adapters_are_accepted(self, adapter_key: str) -> None:
        _check_adapter(adapter_key)  # does not raise

    def test_unknown_adapter_is_rejected_with_a_helpful_message(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _check_adapter("totally-made-up")

        assert exc.value.code == "unknown_adapter"
        assert "worldbank" in exc.value.message
