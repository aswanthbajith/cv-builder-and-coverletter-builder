"""Knowledge-graph layer for M2.

Reads the ``profile/atomic/*.json`` files into a :class:`KnowledgeGraph`,
which exposes:
- ``experiences`` — list of all :class:`AtomicExperience`
- in-memory reverse indexes: skill → exp ids, technology → exp ids, role_family → exp ids
- a lazy-loaded FAISS vector index built by :mod:`job_automation.knowledge.embeddings`

The retriever module (:mod:`job_automation.knowledge.retriever`) consumes this
graph and returns scored atoms for the resume-construction pipeline.

This module is part of the M2 rebuild. The legacy
``job_automation.io.profile_loader.load_profile`` is unchanged.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from job_automation.config import PathsConfig
from job_automation.logging import get_logger
from job_automation.models.atomic import AtomicExperience, RoleFamily

if TYPE_CHECKING:
    from job_automation.knowledge.embeddings import EmbeddingIndex

logger = get_logger(__name__)


class KnowledgeGraph:
    """In-memory knowledge graph built from ``profile/atomic/*.json``.

    Construction reads all files referenced by ``index.json``, validates each
    entry with :class:`AtomicExperience`, and builds the reverse indexes used
    by the retriever. The FAISS vector index is loaded lazily — most
    code-paths only need the categorical indexes.
    """

    def __init__(
        self,
        experiences: list[AtomicExperience],
        *,
        embedding_index: "EmbeddingIndex | None" = None,
    ) -> None:
        # Sort by recency (most recent end first, missing end last) so
        # recent-first traversal is the default.
        self.experiences = sorted(
            experiences,
            key=lambda e: (e.end is None, -(e.end.toordinal() if e.end else 0)),
        )
        self._by_id: dict[str, AtomicExperience] = {e.id: e for e in experiences}

        # Reverse indexes — keep lightweight, no embeddings here.
        self._by_skill: dict[str, list[str]] = defaultdict(list)
        self._by_technology: dict[str, list[str]] = defaultdict(list)
        self._by_role_family: dict[RoleFamily, list[str]] = defaultdict(list)
        self._by_source_ref: dict[str, list[str]] = defaultdict(list)

        for exp in experiences:
            for skill in exp.skills:
                self._by_skill[skill.lower()].append(exp.id)
            for tech in exp.technologies:
                self._by_technology[tech.lower()].append(exp.id)
            for family in exp.role_family_tags:
                self._by_role_family[family].append(exp.id)
            self._by_source_ref[exp.source_ref].append(exp.id)

        self._embedding_index = embedding_index

    # ── Accessors ─────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.experiences)

    def get(self, exp_id: str) -> AtomicExperience | None:
        return self._by_id.get(exp_id)

    def by_skill(self, skill: str) -> list[AtomicExperience]:
        return [self._by_id[i] for i in self._by_skill.get(skill.lower(), [])]

    def by_technology(self, technology: str) -> list[AtomicExperience]:
        return [self._by_id[i] for i in self._by_technology.get(technology.lower(), [])]

    def by_role_family(self, family: RoleFamily) -> list[AtomicExperience]:
        return [self._by_id[i] for i in self._by_role_family.get(family, [])]

    def by_source_ref(self, source_ref: str) -> list[AtomicExperience]:
        return [self._by_id[i] for i in self._by_source_ref.get(source_ref, [])]

    @property
    def embedding_index(self) -> "EmbeddingIndex | None":
        """Lazy-loaded FAISS index. Returns ``None`` if no index has been built."""
        return self._embedding_index

    def with_embeddings(self, embedding_index: "EmbeddingIndex") -> "KnowledgeGraph":
        """Return a copy of this graph with an attached embedding index.

        Used by ``load_knowledge_graph(..., with_embeddings=True)`` so callers
        that don't need semantic search don't pay the cost of loading the
        80 MB MiniLM model.
        """
        return KnowledgeGraph(self.experiences, embedding_index=embedding_index)


def load_knowledge_graph(
    paths: PathsConfig | None = None,
    *,
    with_embeddings: bool = False,
) -> KnowledgeGraph:
    """Read ``profile/atomic/index.json`` and return a :class:`KnowledgeGraph`.

    Follows the same lazy-config pattern as ``load_profile`` — paths default
    to ``load_config().paths``. Each entry in ``index.json`` points to a
    JSON file containing a list of :class:`AtomicExperience` dicts; missing
    files are skipped with a warning.

    Args:
        paths: Optional config override (used by tests).
        with_embeddings: If True, load the FAISS index from
            ``profile/faiss/index.faiss`` if it exists; build it on the fly
            otherwise. If False, the returned graph has no embedding index —
            the retriever will fall back to keyword-only scoring.
    """
    if paths is None:
        from job_automation.config import load_config
        paths = load_config().paths

    profile_dir = Path(paths.profile_dir)
    index_path = profile_dir / "atomic" / "index.json"
    if not index_path.exists():
        logger.error("knowledge_index_missing", extra={"path": str(index_path)})
        return KnowledgeGraph(experiences=[])

    raw = json.loads(index_path.read_text(encoding="utf-8"))
    categories = raw.get("categories", [])
    if not isinstance(categories, list):
        logger.error("knowledge_index_malformed", extra={"path": str(index_path)})
        return KnowledgeGraph(experiences=[])

    collected: list[AtomicExperience] = []
    seen_ids: set[str] = set()
    for entry in categories:
        rel = entry.get("path")
        if not isinstance(rel, str):
            logger.warning("knowledge_index_entry_invalid", extra={"entry": entry})
            continue
        atomic_dir = profile_dir / "atomic"
        file_path = atomic_dir / rel
        if not file_path.exists():
            fallback = profile_dir / rel
            if fallback.exists():
                file_path = fallback
            else:
                logger.warning("knowledge_atom_file_missing", extra={"path": str(file_path)})
                continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("knowledge_atom_file_invalid_json", extra={"path": str(file_path), "error": str(exc)})
            continue
        if not isinstance(data, list):
            logger.warning("knowledge_atom_file_not_list", extra={"path": str(file_path)})
            continue
        for raw_atom in data:
            try:
                atom = AtomicExperience.model_validate(raw_atom)
            except Exception as exc:  # noqa: BLE001 — log and continue, never abort
                logger.warning("knowledge_atom_invalid", extra={"id": raw_atom.get("id", "?"), "error": str(exc)})
                continue
            if atom.id in seen_ids:
                logger.warning("knowledge_atom_duplicate_id", extra={"id": atom.id})
                continue
            seen_ids.add(atom.id)
            collected.append(atom)

    logger.info("knowledge_loaded", extra={"atoms": len(collected)})
    graph = KnowledgeGraph(experiences=collected)

    if with_embeddings:
        from job_automation.knowledge.embeddings import (
            build_or_load_embedding_index,
        )
        index = build_or_load_embedding_index(collected, profile_dir / "faiss")
        return graph.with_embeddings(index)

    return graph


__all__ = ["KnowledgeGraph", "load_knowledge_graph"]