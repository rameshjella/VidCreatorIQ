from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass
class SFXAsset:
    path: Path
    text: str
    vector: list[float]


class SFXSemanticMatcher:
    """Small dependency-free semantic matcher for local SFX libraries.

    It uses hashed token embeddings with corpus-aware IDF weighting. This is
    not as strong as transformer embeddings, but it is deterministic, fast,
    and works offline in constrained runtimes.
    """

    def __init__(self, dims: int = 256):
        self.dims = max(64, int(dims))
        self.assets: list[SFXAsset] = []
        self.idf: dict[str, float] = {}

    def index_library(self, directory: Path) -> list[SFXAsset]:
        files = [
            p for p in sorted(Path(directory).rglob("*")) if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ]
        corpus_tokens: list[set[str]] = []
        metadata: list[tuple[Path, str, list[str]]] = []
        for path in files:
            text = self._describe_asset(path)
            tokens = self._tokenize(text)
            if not tokens:
                continue
            metadata.append((path, text, tokens))
            corpus_tokens.append(set(tokens))

        self.idf = self._compute_idf(corpus_tokens)
        self.assets = [
            SFXAsset(path=path, text=text, vector=self._embed_tokens(tokens))
            for path, text, tokens in metadata
        ]
        return self.assets

    def search(self, query: str, top_k: int = 1) -> list[SFXAsset]:
        if not self.assets:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        q = self._embed_tokens(tokens)
        ranked = sorted(
            self.assets,
            key=lambda asset: self._cosine_similarity(q, asset.vector),
            reverse=True,
        )
        return ranked[: max(1, top_k)]

    def _describe_asset(self, path: Path) -> str:
        parts = [path.stem.replace("_", " "), path.parent.name.replace("_", " ")]
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            try:
                parts.append(sidecar.read_text(encoding="utf-8")[:800])
            except Exception:
                pass
        return " ".join(p for p in parts if p)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall((text or "").lower())

    @staticmethod
    def _compute_idf(corpus_tokens: list[set[str]]) -> dict[str, float]:
        if not corpus_tokens:
            return {}
        doc_count = float(len(corpus_tokens))
        doc_freq: dict[str, int] = {}
        for row in corpus_tokens:
            for token in row:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        return {token: math.log((1.0 + doc_count) / (1.0 + freq)) + 1.0 for token, freq in doc_freq.items()}

    def _embed_tokens(self, tokens: list[str]) -> list[float]:
        vec = [0.0] * self.dims
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        for token, count in tf.items():
            idx = hash(token) % self.dims
            weight = float(count) * self.idf.get(token, 1.0)
            vec[idx] += weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 0:
            return vec
        return [v / norm for v in vec]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return float(sum(x * y for x, y in zip(a, b)))

