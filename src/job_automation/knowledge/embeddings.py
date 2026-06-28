"""Sentence-transformers wrapper for atomic-experience embeddings.

Wraps ``sentence-transformers`` + ``faiss`` behind a lazy import. The
embedding model is ``all-MiniLM-L6-v2`` (384-d, ~80 MB, fast on CPU). The
FAISS index type is ``IndexFlatIP`` on L2-normalized vectors, giving cosine
similarity directly via the inner product.

The module is intentionally small: build the index once via
:func:`build_or_load_embedding_index`, then query with
:meth:`EmbeddingIndex.search`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from job_automation.logging import get_logger
from job_automation.models.atomic import AtomicExperience

logger = get_logger(__name__)

# Module-level lazy state — model load takes ~5s and 80 MB.
_MODEL: object | None = None
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _get_model() -> object:
    """Return the cached sentence-transformers model, loading on first call."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        logger.info("embedding_model_loading", extra={"model": _MODEL_NAME})
        _MODEL = SentenceTransformer(_MODEL_NAME)
        logger.info("embedding_model_loaded")
    return _MODEL


class EmbeddingIndex:
    """FAISS-backed nearest-neighbor index over atomic experiences.

    The index stores L2-normalized vectors; ``search`` returns cosine
    similarity scores in ``[0, 1]`` for unit vectors.
    """

    def __init__(self, ids: list[str], vectors: np.ndarray) -> None:
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        self.ids = list(ids)
        self._index = _build_faiss_index(vectors)

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Return up to ``top_k`` (id, cosine_similarity) pairs, descending."""
        if not self.ids or self._index is None:
            return []
        model = _get_model()
        q_vec = model.encode([query], normalize_embeddings=True).astype(np.float32)
        scores, indices = self._index.search(q_vec, min(top_k, len(self.ids)))
        out: list[tuple[str, float]] = []
        for idx, score in zip(indices[0], scores[0], strict=False):
            if idx < 0 or idx >= len(self.ids):
                continue
            out.append((self.ids[int(idx)], float(score)))
        return out


def _build_faiss_index(vectors: np.ndarray) -> object:
    """Build a flat inner-product FAISS index. Returns ``None`` if FAISS unavailable."""
    try:
        import faiss  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("faiss_unavailable_falling_back_to_brute_force")
        return None

    dim = vectors.shape[1] if vectors.ndim == 2 else 0
    if dim == 0:
        return None
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def build_or_load_embedding_index(
    experiences: list[AtomicExperience],
    faiss_dir: Path,
) -> EmbeddingIndex | None:
    """Build a new FAISS index or load one from disk.

    If ``faiss_dir/index.faiss`` exists and ``faiss_dir/ids.json`` exists with
    matching atom ids, load from disk. Otherwise build and persist. Returns
    ``None`` if there are no experiences or if sentence-transformers is not
    installed.
    """
    if not experiences:
        return None

    faiss_dir.mkdir(parents=True, exist_ok=True)
    index_path = faiss_dir / "index.faiss"
    ids_path = faiss_dir / "ids.json"

    if index_path.exists() and ids_path.exists():
        try:
            disk_ids = json_load_ids(ids_path)
            if disk_ids == [e.id for e in experiences]:
                logger.info("embedding_index_loaded", extra={"path": str(index_path)})
                vectors = _load_faiss_vectors(index_path)
                if vectors is not None:
                    return EmbeddingIndex(disk_ids, vectors)
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding_index_load_failed", extra={"error": str(exc)})

    return _build_and_persist(experiences, index_path, ids_path)


def _build_and_persist(
    experiences: list[AtomicExperience],
    index_path: Path,
    ids_path: Path,
) -> EmbeddingIndex | None:
    """Encode atoms and persist the FAISS index + ids file."""
    try:
        model = _get_model()
        texts = [e.embedding_text for e in experiences]
        vectors = model.encode(texts, normalize_embeddings=True).astype(np.float32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding_build_failed", extra={"error": str(exc)})
        return None

    ids = [e.id for e in experiences]
    _persist_faiss(vectors, index_path)
    ids_path.write_text(json_dumps_ids(ids), encoding="utf-8")
    logger.info("embedding_index_built", extra={"atoms": len(ids), "path": str(index_path)})
    return EmbeddingIndex(ids, vectors)


def _persist_faiss(vectors: np.ndarray, path: Path) -> None:
    """Persist FAISS index if FAISS is available, else no-op."""
    try:
        import faiss  # type: ignore[import-not-found]

        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        faiss.write_index(index, str(path))
    except ImportError:
        logger.warning("faiss_unavailable_skipping_persist")


def _load_faiss_vectors(path: Path) -> np.ndarray | None:
    try:
        import faiss  # type: ignore[import-not-found]

        index = faiss.read_index(str(path))
        return _index_to_vectors(index)
    except ImportError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("faiss_read_failed", extra={"path": str(path), "error": str(exc)})
        return None


def _index_to_vectors(index: object) -> np.ndarray:
    """Reconstruct the (n, d) vector array from a flat FAISS index."""
    n = int(index.ntotal)  # type: ignore[attr-defined]
    d = int(index.d)  # type: ignore[attr-defined]
    out = np.zeros((n, d), dtype=np.float32)
    for i in range(n):
        out[i] = index.reconstruct(i)  # type: ignore[attr-defined]
    return out


# Tiny indirection so we can monkeypatch in tests without importing json everywhere.
def json_load_ids(path: Path) -> list[str]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def json_dumps_ids(ids: list[str]) -> str:
    import json

    return json.dumps(ids, indent=2)


__all__ = ["EmbeddingIndex", "build_or_load_embedding_index"]