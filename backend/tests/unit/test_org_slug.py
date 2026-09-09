"""Slug generation from organization names."""

from __future__ import annotations

import pytest

from app.modules.orgs.service import SLUG_MAX_LENGTH, slugify


class TestSlugify:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Grameen Bank", "grameen-bank"),
            ("BRAC IT Services Ltd.", "brac-it-services-ltd"),
            ("ACME", "acme"),
            ("  Padded  Name  ", "padded-name"),
            ("Multi   internal    spaces", "multi-internal-spaces"),
            ("Beximco & Co.", "beximco-co"),
            ("A/B Testing, Inc.", "a-b-testing-inc"),
            ("Square 2025", "square-2025"),
            ("under_score", "under-score"),
            ("Already-Hyphenated", "already-hyphenated"),
        ],
    )
    def test_common_names(self, name: str, expected: str) -> None:
        assert slugify(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Café Ltd", "cafe-ltd"),
            ("Zürich Söhne", "zurich-sohne"),
            ("Ångström Måleri", "angstrom-maleri"),
            ("Crème Brûlée", "creme-brulee"),
        ],
    )
    def test_accents_fold_to_ascii(self, name: str, expected: str) -> None:
        assert slugify(name) == expected

    @pytest.mark.parametrize("name", ["", "   ", "  ---  ", "!!!", "@#$%^&*()", "…", "বাংলা"])
    def test_nothing_usable_falls_back(self, name: str) -> None:
        """Names with no ASCII alphanumerics still produce a valid slug."""
        assert slugify(name) == "org"

    def test_long_names_are_truncated(self) -> None:
        slug = slugify("Bangladesh Rural Advancement Committee Information Technology Services")

        assert len(slug) <= SLUG_MAX_LENGTH
        assert slug == "bangladesh-rural-advancement-committee-information"

    def test_truncation_never_leaves_a_trailing_hyphen(self) -> None:
        # The 50-character cut falls exactly on the space before "Ltd".
        slug = slugify(f"{'a' * 49} Ltd")

        assert len(slug) <= SLUG_MAX_LENGTH
        assert not slug.endswith("-")
        assert slug == "a" * 49

    def test_result_is_always_url_safe(self) -> None:
        for name in ["Grameen Bank", "Café Ltd", "!!!", "A/B Testing, Inc."]:
            slug = slugify(name)

            assert slug
            assert slug == slug.lower()
            assert all(char.isalnum() or char == "-" for char in slug)
            assert "--" not in slug
            assert not slug.startswith("-")
            assert not slug.endswith("-")
