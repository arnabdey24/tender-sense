"""Gemini-backed embeddings and structured generation.

Three things here are not obvious and are deliberate:

* **No `task_type`.** `gemini-embedding-2` rejects it; the document/query
  asymmetry is carried in prompt prefixes instead (see :mod:`app.ai.base`). The
  legacy `gemini-embedding-001` does take `task_type`, so it is only used as a
  configured fallback and gets the parameter when it is.
* **Truncated vectors are re-normalised.** Asking for 768 dimensions out of a
  larger native size returns a vector that is no longer unit length, and cosine
  distance in pgvector assumes it is.
* **One limiter, one semaphore, process-wide.** The free tier is measured in
  requests per minute, and a worker running several tenders concurrently would
  otherwise burn the quota in seconds.
* **Batching is opt-in per model.** `gemini-embedding-2` accepts a list of
  contents and returns a single embedding for it, discarding the rest without
  an error — which would silently pair the wrong vector with the wrong chunk.
  Only models proven to batch get a multi-content request.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from aiolimiter import AsyncLimiter
from anyio import Semaphore
from google import genai
from google.genai import types
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.base import (
    AIError,
    EmbeddingResult,
    GenerationResult,
    GroundedResult,
    Usage,
    document_text,
    query_text,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Model ids that still take the legacy `task_type` parameter.
_TASK_TYPE_MODELS = frozenset({"gemini-embedding-001"})

#: Model ids verified to return one embedding per input when given a list.
#: Everything else is called one text at a time — see `_embed`. Confirmed by
#: `tests/live/test_gemini_live.py::TestEmbeddings::test_a_batch_returns_one_vector_per_text`.
_BATCHING_MODELS = frozenset({"gemini-embedding-001"})

RETRYABLE = (AIError,)


def _normalise(vector: list[float]) -> list[float]:
    """Rescale to unit length.

    Requesting fewer dimensions than the model's native size truncates the
    vector, which breaks the unit-length assumption cosine distance relies on.
    """
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        raise AIError("Embedding came back as a zero vector.")
    if math.isclose(norm, 1.0, rel_tol=1e-6):
        return vector
    return [component / norm for component in vector]


class GeminiClient:
    """Implements :class:`~app.ai.base.AIClient` against Google's API."""

    def __init__(
        self,
        *,
        api_key: str,
        embedding_model: str | None = None,
        generation_model: str | None = None,
        dims: int | None = None,
        requests_per_minute: int | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.embedding_model = embedding_model or settings.embedding_model
        self.generation_model = generation_model or settings.generation_model
        self.dims = dims or settings.embedding_dims
        rpm = requests_per_minute or settings.ai_requests_per_minute
        self._limiter = AsyncLimiter(max_rate=rpm, time_period=60)
        self._semaphore = Semaphore(max_concurrency or settings.ai_max_concurrency)

    # -- embeddings --------------------------------------------------------

    async def embed_documents(
        self, texts: list[str], *, titles: list[str] | None = None
    ) -> EmbeddingResult:
        names = titles or [""] * len(texts)
        if len(names) != len(texts):
            raise AIError("titles must line up with texts.")
        prepared = [document_text(title, body) for title, body in zip(names, texts, strict=True)]
        return await self._embed(prepared, task_type="RETRIEVAL_DOCUMENT")

    async def embed_queries(self, texts: list[str]) -> EmbeddingResult:
        return await self._embed([query_text(text) for text in texts], task_type="RETRIEVAL_QUERY")

    async def _embed(self, texts: list[str], *, task_type: str) -> EmbeddingResult:
        """Embed a batch, one request per text unless the model truly batches.

        `gemini-embedding-2` accepts a list of contents and returns a **single**
        embedding for it, silently discarding the rest. Nothing errors, so a
        batched call would hand chunk B's vector to chunk A and every match
        score downstream would be quietly wrong. Only models known to batch
        correctly get a multi-content request; everything else fans out.
        """
        if not texts:
            raise AIError("Nothing to embed.")

        started = time.perf_counter()

        if self.embedding_model in _BATCHING_MODELS:
            vectors, tokens = await self._embed_call(texts, task_type=task_type)
        else:
            results = await asyncio.gather(
                *(self._embed_call([text], task_type=task_type) for text in texts)
            )
            vectors = [vector for chunk, _ in results for vector in chunk]
            tokens = sum(count for _, count in results)

        if len(vectors) != len(texts):
            raise AIError(f"Asked for {len(texts)} embeddings, got {len(vectors)}.")

        return EmbeddingResult(
            vectors=vectors,
            model=self.embedding_model,
            dims=self.dims,
            usage=Usage(
                model=self.embedding_model,
                tokens_in=tokens,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )

    @retry(
        retry=retry_if_exception_type(RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _embed_call(
        self, texts: list[str], *, task_type: str
    ) -> tuple[list[list[float]], int]:
        """One request. Retried on its own, so a flaky text cannot fail a batch."""
        config: dict[str, Any] = {"output_dimensionality": self.dims}
        # Only the legacy model understands task_type; the current one 400s on it.
        if self.embedding_model in _TASK_TYPE_MODELS:
            config["task_type"] = task_type

        async with self._semaphore, self._limiter:
            try:
                response = await self._client.aio.models.embed_content(
                    model=self.embedding_model,
                    contents=texts,
                    config=types.EmbedContentConfig(**config),
                )
            except Exception as exc:
                raise AIError(f"Embedding call failed: {exc}") from exc

        embeddings = response.embeddings or []
        vectors: list[list[float]] = []
        for embedding in embeddings:
            values = embedding.values
            if not values:
                raise AIError("Embedding came back empty.")
            vectors.append(_normalise(list(values)))
        return vectors, _token_count(response)

    # -- generation --------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
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
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
        )

        started = time.perf_counter()
        async with self._semaphore, self._limiter:
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.generation_model, contents=prompt, config=config
                )
            except Exception as exc:
                raise AIError(f"Generation call failed: {exc}") from exc

        parsed = response.parsed
        if parsed is None:
            raise AIError("Model returned no parseable JSON.")
        if not isinstance(parsed, schema):
            # The SDK hands back a dict when it cannot bind the schema itself.
            try:
                parsed = schema.model_validate(parsed)
            except Exception as exc:
                raise AIError(f"Model output did not match {schema.__name__}: {exc}") from exc

        usage = response.usage_metadata
        return GenerationResult(
            parsed=parsed,
            raw_text=response.text or "",
            usage=Usage(
                model=self.generation_model,
                tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
                tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )

    async def generate_grounded[M: BaseModel](
        self,
        *,
        prompt: str,
        schema: type[M],
        urls: list[str],
        system_instruction: str | None = None,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> GroundedResult[M]:
        """Structured generation that may read the web pages it is given.

        Two things here were learned the hard way against the live API and are
        the reason this is not just `generate_structured` with a tool bolted on.

        **`max_output_tokens` is mandatory, not a tuning knob.** Left unset,
        `gemini-3.8-flash` re-fetched one URL twenty-four times and terminated
        with `TOO_MANY_TOOL_CALLS` and an empty body — a total failure, several
        seconds of latency, and a bill. Capped, the same call returns first
        time. The default below is generous for the schemas we ask for and
        still well inside the loop.

        **The retrieval status is the only honest answer to "did it read the
        page".** The provider reports it per URL, out of band from anything the
        model wrote, and it is the one signal a model cannot talk itself into.
        Asked about a domain that does not resolve, a model will write a
        plausible company from the name; this refuses to pass that on.
        """
        config = types.GenerateContentConfig(
            tools=[types.Tool(url_context=types.UrlContext())],
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens or settings.research_max_output_tokens,
        )

        started = time.perf_counter()
        async with self._semaphore, self._limiter:
            try:
                response = await self._client.aio.models.generate_content(
                    model=settings.research_model, contents=prompt, config=config
                )
            except Exception as exc:
                raise AIError(f"Grounded generation failed: {exc}") from exc

        candidates = response.candidates or []
        candidate = candidates[0] if candidates else None
        finish = getattr(candidate, "finish_reason", None)
        if finish is not None and str(finish).endswith("TOO_MANY_TOOL_CALLS"):
            raise AIError("The model kept re-reading the page and gave up.")

        retrieved = _retrieved_urls(candidate)

        parsed = response.parsed
        if parsed is None:
            raise AIError("Model returned no parseable JSON.")
        if not isinstance(parsed, schema):
            try:
                parsed = schema.model_validate(parsed)
            except Exception as exc:
                raise AIError(f"Model output did not match {schema.__name__}: {exc}") from exc

        usage = response.usage_metadata
        return GroundedResult(
            parsed=parsed,
            raw_text=response.text or "",
            retrieved_urls=retrieved,
            usage=Usage(
                model=settings.research_model,
                tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
                tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )

    async def healthcheck(self) -> bool:
        try:
            await self._embed(["ping"], task_type="RETRIEVAL_QUERY")
        except Exception as exc:
            logger.warning("gemini_healthcheck_failed", error=str(exc))
            return False
        return True


def _retrieved_urls(candidate: Any) -> list[str]:
    """URLs the provider reports it actually fetched, deduplicated in order.

    A single page routinely appears several times when the model re-reads it,
    and only a `SUCCESS` counts — an `ERROR` entry means the fetch failed, and
    a failed fetch beside confident prose is the case this exists to catch.
    """
    metadata = getattr(candidate, "url_context_metadata", None)
    entries = getattr(metadata, "url_metadata", None) or []
    seen: list[str] = []
    for entry in entries:
        status = str(getattr(entry, "url_retrieval_status", ""))
        url = getattr(entry, "retrieved_url", "") or ""
        if url and status.endswith("SUCCESS") and url not in seen:
            seen.append(url)
    return seen


def _token_count(response: Any) -> int:
    """Embedding responses report billing differently across model versions."""
    metadata = getattr(response, "metadata", None)
    return int(getattr(metadata, "billable_character_count", 0) or 0)
