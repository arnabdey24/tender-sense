"""The extraction prompt.

Kept as a module rather than a template file because it is versioned alongside
:data:`~app.ai.schemas.EXTRACTION_PROMPT_VERSION`, and every stored extraction
records which version produced it — so a scoring decision stays explainable
after the wording changes.
"""

from __future__ import annotations

SYSTEM_INSTRUCTION = """\
You read public procurement notices and pull out the facts a bidder needs.

Rules you must follow:
- Only report what the notice actually says. Never infer a requirement from what
  is typical for this kind of contract.
- If a field is not stated, omit it. An omitted field is correct; a guessed one
  is a costly error, because a missing requirement makes a company look eligible
  when it is not, and an invented one hides a tender it could have won.
- For every field you do report, give a confidence between 0 and 1 and a short
  verbatim quote from the notice as evidence.
- Money keeps the currency the notice uses. Do not convert.
- Countries are ISO 3166-1 alpha-2 codes. Leave the list empty when the notice
  places no restriction on where bidders come from.
- Quotes must be copied from the notice, not paraphrased.
"""


def build_prompt(
    *,
    title: str,
    procuring_entity: str | None,
    country: str | None,
    category: str | None,
    method: str | None,
    summary: str | None,
    description: str | None,
) -> str:
    """Assemble the user-side prompt for one notice."""
    parts = [
        "Extract the structured attributes of this procurement notice.",
        "",
        f"Title: {title}",
    ]
    if procuring_entity:
        parts.append(f"Procuring entity: {procuring_entity}")
    if country:
        parts.append(f"Country: {country}")
    if category:
        parts.append(f"Category: {category}")
    if method:
        parts.append(f"Procurement method: {method}")
    if summary:
        parts += ["", "Summary:", summary]
    if description:
        parts += ["", "Notice text:", description]
    return "\n".join(parts)
