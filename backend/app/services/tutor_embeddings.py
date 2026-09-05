from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol


class TutorEmbeddingUnavailable(RuntimeError):
    pass


class TutorEmbeddingFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class TutorEmbeddingConfig:
    provider: str = "none"
    openai_api_key: str | None = None
    openai_model: str = "text-embedding-3-small"
    max_candidates: int = 128
    batch_size: int = 64


class TutorEmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise TutorEmbeddingUnavailable("OpenAI embedding provider is not configured")
        self.model = model
        self.name = f"openai-embeddings:{model}"
        self._client = client
        self._api_key = api_key

    def _client_instance(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - packaging protects this path
            raise TutorEmbeddingUnavailable("OpenAI SDK is not installed") from exc
        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client_instance().embeddings.create(
                model=self.model,
                input=texts,
                encoding_format="float",
            )
        except Exception as exc:
            raise TutorEmbeddingFailure("OpenAI embedding request failed") from exc

        vectors = [list(item.embedding) for item in response.data]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise TutorEmbeddingFailure("Embedding provider returned an invalid vector batch")
        return vectors


def build_embedding_provider(
    config: TutorEmbeddingConfig,
) -> TutorEmbeddingProvider | None:
    if config.provider == "none":
        return None
    if config.provider == "openai":
        if not config.openai_api_key:
            raise TutorEmbeddingUnavailable(
                "OpenAI semantic retrieval requires OPENAI_API_KEY"
            )
        return OpenAIEmbeddingProvider(
            api_key=config.openai_api_key,
            model=config.openai_model,
        )
    raise TutorEmbeddingUnavailable(f"Unsupported embedding provider: {config.provider}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    denominator = left_norm * right_norm
    if denominator <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, numerator / denominator))
