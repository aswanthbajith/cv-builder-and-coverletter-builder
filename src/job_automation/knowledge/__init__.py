"""Knowledge-graph module — M2.

Public surface:

- :class:`KnowledgeGraph` — in-memory index over :class:`AtomicExperience`
- :func:`load_knowledge_graph` — reads ``profile/atomic/index.json``
- :class:`EmbeddingIndex` — FAISS-backed nearest-neighbor search
- :func:`find_relevant_experiences` — main retrieval entry point
- :func:`detect_role_family` — heuristic job classification
"""

from __future__ import annotations

from job_automation.knowledge.embeddings import (
    EmbeddingIndex,
    build_or_load_embedding_index,
)
from job_automation.knowledge.graph import KnowledgeGraph, load_knowledge_graph
from job_automation.knowledge.retriever import (
    detect_role_family,
    find_relevant_experiences,
    group_by_source_ref,
)

__all__ = [
    "EmbeddingIndex",
    "KnowledgeGraph",
    "build_or_load_embedding_index",
    "detect_role_family",
    "find_relevant_experiences",
    "group_by_source_ref",
    "load_knowledge_graph",
]