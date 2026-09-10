"""Comparison keys for text that people type inconsistently.

Certifications are the reason this exists. "ISO 9001", "iso-9001" and
"ISO 9001:2015" are the same credential, and a rule asking whether a company
holds it must not turn on how somebody typed it. The profile stores the folded
form and the engine compares the folded form, so both have to fold identically
— which is why this lives in one place rather than being reimplemented in each.
"""

from __future__ import annotations


def comparison_key(value: str) -> str:
    """Fold a label to a stable key.

    Drops any revision suffix after a colon ("ISO 9001:2015" -> ISO9001), then
    everything that is not alphanumeric, then upper-cases what is left.
    """
    head = value.split(":", 1)[0]
    return "".join(character for character in head if character.isalnum()).upper()
