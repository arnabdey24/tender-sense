"""A deterministic stand-in for Gemini.

Every output is derived from a SHA-256 of the input, so the same text always
produces the same vector and the same attributes. That gives the test suite and
the seed script a full matching pipeline — extraction, embedding, scoring,
grading, explanations — with no API key, no network and no rate limit, and it
makes matching assertions stable across runs.

The vectors are not meaningful, with one deliberate exception: texts that share
vocabulary land closer together, because each token contributes to the same
dimensions. That is enough for "a related tender scores above an unrelated one"
to hold, which is what the matching tests actually assert.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Any, cast

from pydantic import BaseModel

from app.ai.base import AIError, EmbeddingResult, GenerationResult, Usage
from app.ai.schemas import (
    FieldEvidence,
    MatchExplanation,
    Money,
    Sector,
    TenderAttributes,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

FAKE_EMBEDDING_MODEL = "fake-embedding-1"
FAKE_GENERATION_MODEL = "fake-generation-1"

#: Function words carry no topical signal, but a hash projection cannot know
#: that — it would score "supply *of* switches" against "printing *of* books"
#: on the strength of "of". A real embedding model has learned to ignore them;
#: the fake has to be told. Also covers the prompt-prefix words this module's
#: own callers add ("title", "text", "query", "task", "search", "result").
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "of",
        "for",
        "to",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "our",
        "your",
        "his",
        "her",
        "they",
        "we",
        "you",
        "i",
        "he",
        "she",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "then",
        "than",
        "there",
        "here",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "too",
        "very",
        "can",
        "will",
        "just",
        "should",
        "now",
        "shall",
        "may",
        "might",
        "must",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "having",
        "into",
        "over",
        "under",
        "again",
        "further",
        "once",
        "about",
        "against",
        "between",
        "during",
        "before",
        "after",
        "above",
        "below",
        "up",
        "down",
        "out",
        "off",
        "through",
        "title",
        "text",
        "query",
        "task",
        "search",
        "result",
    ]
)


def _tokens(text: str) -> list[str]:
    """Content words only, so shared function words cannot fake a match."""
    found = _TOKEN_RE.findall(text.lower())
    content = [token for token in found if token not in _STOPWORDS]
    # A string made entirely of stopwords still has to embed to something.
    return content or found


def _digest_floats(seed: str, count: int) -> list[float]:
    """A deterministic stream of floats in [-1, 1) derived from ``seed``."""
    out: list[float] = []
    counter = 0
    while len(out) < count:
        block = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        for i in range(0, len(block), 4):
            if len(out) >= count:
                break
            word = int.from_bytes(block[i : i + 4], "big")
            out.append(word / 2**31 - 1.0)
        counter += 1
    return out


def deterministic_embedding(text: str, dims: int) -> list[float]:
    """Bag-of-tokens projection: shared vocabulary means a higher cosine.

    Each distinct token is hashed to a handful of dimensions it contributes to.
    Two texts about "network infrastructure" therefore overlap, while a text
    about "textbook printing" does not — without needing a real model.
    """
    vector = [0.0] * dims
    tokens = _tokens(text)
    if not tokens:
        # An empty string still needs a unit vector; anything else divides by 0.
        vector[0] = 1.0
        return vector

    for token in tokens:
        weights = _digest_floats(token, 8)
        digest = hashlib.sha256(token.encode()).digest()
        for slot in range(8):
            index = int.from_bytes(digest[slot * 4 : slot * 4 + 4], "big") % dims
            vector[index] += weights[slot]

    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:  # pragma: no cover - only reachable if every weight cancels
        vector[0] = 1.0
        return vector
    return [component / norm for component in vector]


def _pick[T](options: list[T], seed: str) -> T:
    index = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:4], "big")
    return options[index % len(options)]


def _chance(seed: str) -> float:
    """A stable 0..1 draw for one decision."""
    return int.from_bytes(hashlib.sha256(seed.encode()).digest()[:4], "big") / 2**32


def fake_attributes(text: str) -> TenderAttributes:
    """Plausible, stable attributes for a notice.

    Sectors come from keywords where the text has them, so a fake extraction of
    an IT tender really does say "it" — otherwise the matching tests would be
    asserting against noise.
    """
    lowered = text.lower()
    keyword_sectors = {
        Sector.IT: ("software", "system", "network", "data", "digital", "mis", "ict"),
        Sector.CONSTRUCTION: ("construction", "building", "road", "bridge", "civil", "works"),
        Sector.HEALTHCARE: ("health", "hospital", "medical", "pharmaceutical", "clinic"),
        Sector.EDUCATION: ("school", "education", "textbook", "training", "university"),
        Sector.ENERGY: ("solar", "power", "electric", "energy", "grid"),
        Sector.WATER: ("water", "irrigation", "sanitation", "drainage"),
        Sector.TRANSPORT: ("transport", "vehicle", "railway", "port", "dredging"),
    }
    sectors = [
        sector
        for sector, words in keyword_sectors.items()
        if any(word in lowered for word in words)
    ][:3] or [Sector.OTHER]

    seed = hashlib.sha256(text.encode()).hexdigest()
    turnover = _pick([None, 5_000_000.0, 20_000_000.0, 80_000_000.0], f"{seed}:turnover")
    certifications = _pick(
        [[], ["ISO 9001"], ["ISO 9001", "ISO 27001"], ["CMMI-3"]], f"{seed}:certs"
    )
    years = _pick([None, 3, 5, 10], f"{seed}:years")

    body = _notice_body(text)

    attributes = TenderAttributes(
        sectors=sectors,
        scope_summary=body[:280] or None,
        key_deliverables=[line.strip() for line in body.splitlines() if line.strip()][:3],
        required_qualifications_text=None,
        min_annual_turnover=(
            Money(amount=turnover, currency="BDT") if turnover is not None else None
        ),
        required_certifications=certifications,
        eligible_countries=_pick([[], ["BD"], ["BD", "NP", "LK"]], f"{seed}:countries"),
        min_years_experience=years,
        similar_projects_required=_pick([None, 1, 2, 3], f"{seed}:similar"),
        jv_allowed=_chance(f"{seed}:jv") > 0.35,
        local_registration_required=_chance(f"{seed}:local") > 0.6,
    )

    # Confidence mirrors what a real extraction looks like: high where the field
    # was actually stated, low-but-present where it was inferred.
    stated = {
        "sectors": 0.9,
        "scope_summary": 0.85,
        "min_annual_turnover": 0.75 if turnover is not None else 0.2,
        "required_certifications": 0.7 if certifications else 0.3,
        "eligible_countries": 0.6,
        "min_years_experience": 0.7 if years is not None else 0.2,
        "similar_projects_required": 0.55,
        "jv_allowed": 0.5,
        "local_registration_required": 0.45,
    }
    attributes.field_evidence = [
        FieldEvidence(
            field=field,
            confidence=score,
            quote=body[:120] if score >= 0.5 else None,
        )
        for field, score in stated.items()
    ]
    return attributes


#: Field labels the extraction prompt adds around the notice. They are prompt
#: scaffolding, not something the buyer wrote.
_PROMPT_LABELS = (
    "Title:",
    "Procuring entity:",
    "Country:",
    "Category:",
    "Procurement method:",
)


def _notice_body(prompt: str) -> str:
    """The notice itself, with the instruction line and field labels removed.

    ``fake_attributes`` is handed the whole prompt, so deriving a scope summary,
    key deliverables or an evidence quote from it verbatim used to echo
    "Extract the structured attributes of this procurement notice." back out as
    though the notice had said it — and that text was then stored on the
    extraction and rendered to bidders as a requirement.
    """
    for marker in ("\nNotice text:\n", "\nSummary:\n"):
        _, separator, tail = prompt.partition(marker)
        if separator and tail.strip():
            return tail.strip()

    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    kept = [
        line
        for line in lines
        if not line.startswith("Extract the structured attributes")
    ]
    # Nothing but labelled fields left: prefer the title's value over its label.
    for line in kept:
        if line.startswith("Title:"):
            return line[len("Title:") :].strip()
    return "\n".join(
        line for line in kept if not line.startswith(_PROMPT_LABELS)
    ).strip()


def fake_explanation(prompt: str) -> MatchExplanation:
    return MatchExplanation(
        summary="Deterministic explanation generated without calling a model.",
        why_matched=["Shared vocabulary between the notice and the profile."],
        gaps=[],
        risks=[],
        next_step="Review the requirements tab.",
    )


class FakeAIClient:
    """Implements :class:`~app.ai.base.AIClient` with no I/O."""

    def __init__(
        self,
        dims: int = 768,
        *,
        fail: bool = False,
        fail_generation: bool = False,
        fail_embedding: bool = False,
    ) -> None:
        self.embedding_model = FAKE_EMBEDDING_MODEL
        self.generation_model = FAKE_GENERATION_MODEL
        self.dims = dims
        #: Embedding and generation are separate endpoints and fail
        #: independently in practice — an extraction outage does not stop a
        #: notice being embedded and matched. `fail` breaks both; the narrower
        #: flags exercise one degraded path at a time.
        self.fail_generation = fail or fail_generation
        self.fail_embedding = fail or fail_embedding
        #: Every prompt seen, so tests can assert on what was asked.
        self.calls: list[dict[str, Any]] = []

    async def embed_documents(
        self, texts: list[str], *, titles: list[str] | None = None
    ) -> EmbeddingResult:
        return self._embed(texts, kind="document")

    async def embed_queries(self, texts: list[str]) -> EmbeddingResult:
        return self._embed(texts, kind="query")

    def _embed(self, texts: list[str], *, kind: str) -> EmbeddingResult:
        started = time.perf_counter()
        self.calls.append({"op": "embed", "kind": kind, "count": len(texts)})
        if self.fail_embedding:
            raise AIError("FakeAIClient is configured to fail embedding.")
        vectors = [deterministic_embedding(text, self.dims) for text in texts]
        return EmbeddingResult(
            vectors=vectors,
            model=self.embedding_model,
            dims=self.dims,
            usage=Usage(
                model=self.embedding_model,
                tokens_in=sum(len(_tokens(text)) for text in texts),
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )

    async def generate_structured[M: BaseModel](
        self,
        *,
        prompt: str,
        schema: type[M],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> GenerationResult[M]:
        self.calls.append({"op": "generate", "schema": schema.__name__, "prompt": prompt})
        if self.fail_generation:
            raise AIError("FakeAIClient is configured to fail generation.")

        if schema is TenderAttributes:
            parsed: BaseModel = fake_attributes(prompt)
        elif schema is MatchExplanation:
            parsed = fake_explanation(prompt)
        else:  # pragma: no cover - a new schema must add a branch here
            parsed = schema()

        return GenerationResult(
            parsed=cast("M", parsed),
            raw_text=parsed.model_dump_json(),
            usage=Usage(
                model=self.generation_model,
                tokens_in=len(_tokens(prompt)),
                tokens_out=64,
                latency_ms=1,
            ),
        )

    async def healthcheck(self) -> bool:
        return not (self.fail_generation or self.fail_embedding)
