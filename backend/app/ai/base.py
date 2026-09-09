"""The contract every AI backend implements.

Two implementations exist: :mod:`app.ai.gemini_client` talks to Gemini, and
:mod:`app.ai.fake_client` produces deterministic vectors and attributes from a
hash of the input. The fake is what lets the whole matching pipeline —
extraction, embedding, scoring, grading — be tested end to end without a network
call, an API key, or a rate limit.

Callers depend on this protocol, never on a concrete client, so swapping the
provider is a configuration change rather than a refactor.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

#: Prefix applied to text being stored, per the embedding model's guidance.
#: `gemini-embedding-2` takes no `task_type`, so the asymmetry between a
#: document and a query has to be carried in the text itself.
DOCUMENT_PREFIX_TEMPLATE = "title: {title} | text: {text}"
QUERY_PREFIX_TEMPLATE = "task: search result | query: {text}"


class Usage(BaseModel):
    """Tokens and latency for one call, recorded per row for cost tracking."""

    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class EmbeddingResult(BaseModel):
    vectors: list[list[float]]
    model: str
    dims: int
    usage: Usage


class GenerationResult[T: BaseModel](BaseModel):
    """A structured generation, already parsed into the requested model."""

    parsed: T
    raw_text: str = ""
    usage: Usage


class AIError(Exception):
    """A call failed in a way the caller is expected to handle.

    Extraction and explanation both degrade rather than fail the pipeline: a
    tender with no extraction is still embeddable and matchable, just with
    lower-confidence eligibility.
    """


class BudgetExceededError(AIError):
    """The daily token budget is spent; fall back to non-AI behaviour."""


@runtime_checkable
class AIClient(Protocol):
    """One provider of embeddings and structured generation."""

    embedding_model: str
    generation_model: str
    dims: int

    async def embed_documents(
        self, texts: list[str], *, titles: list[str] | None = None
    ) -> EmbeddingResult:
        """Embed text that will be stored and searched against."""
        ...

    async def embed_queries(self, texts: list[str]) -> EmbeddingResult:
        """Embed text being used as the search side of a comparison."""
        ...

    async def generate_structured[M: BaseModel](
        self,
        *,
        prompt: str,
        schema: type[M],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> GenerationResult[M]:
        """Generate JSON conforming to ``schema`` and return it parsed."""
        ...

    async def healthcheck(self) -> bool:
        """Cheap reachability probe."""
        ...


class AIUsageTally(BaseModel):
    """Running total a job accumulates so one row can be written per run."""

    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    by_model: dict[str, int] = Field(default_factory=dict)

    def add(self, usage: Usage) -> None:
        self.calls += 1
        self.tokens_in += usage.tokens_in
        self.tokens_out += usage.tokens_out
        total = usage.tokens_in + usage.tokens_out
        self.by_model[usage.model] = self.by_model.get(usage.model, 0) + total

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


def document_text(title: str | None, body: str | None) -> str:
    """Build the stored-side text for an embedding call."""
    return DOCUMENT_PREFIX_TEMPLATE.format(title=(title or "").strip(), text=(body or "").strip())


def query_text(text: str) -> str:
    """Build the query-side text for an embedding call."""
    return QUERY_PREFIX_TEMPLATE.format(text=text.strip())


def coerce_json_object(value: Any) -> dict[str, Any]:
    """Normalise a parsed model or mapping into a plain JSON-able dict."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    raise AIError(f"Expected an object, got {type(value).__name__}.")
