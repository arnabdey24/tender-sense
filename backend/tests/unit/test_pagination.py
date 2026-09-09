from __future__ import annotations

from app.core.pagination import Page, PageParams


def test_offset_is_zero_on_the_first_page() -> None:
    assert PageParams(page=1, page_size=25).offset == 0


def test_offset_advances_by_page_size() -> None:
    assert PageParams(page=3, page_size=20).offset == 40


def test_build_carries_pagination_metadata() -> None:
    page = Page[str].build(["a", "b"], PageParams(page=2, page_size=2), total=7)

    assert (page.items, page.page, page.page_size, page.total) == (["a", "b"], 2, 2, 7)
