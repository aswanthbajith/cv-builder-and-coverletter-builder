"""Build the FAISS embedding index for the knowledge graph.

Run this once after editing ``profile/atomic/*.json``. The script reads the
same files the runtime uses, encodes each atom's ``embedding_text`` with
``sentence-transformers/all-MiniLM-L6-v2``, and persists a flat inner-product
index plus the id ordering to ``profile/faiss/``.

Usage:

    python scripts/build_knowledge_index.py
    python scripts/build_knowledge_index.py --profile-dir /path/to/profile
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("profile"),
        help="Path to the profile directory containing atomic/ (default: profile/).",
    )
    args = parser.parse_args()

    # Add src/ to sys.path so job_automation imports work whether the
    # package is installed in editable mode or used from a working tree.
    project_root = Path(__file__).resolve().parent.parent
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from job_automation.config import PathsConfig
    from job_automation.knowledge import load_knowledge_graph
    from job_automation.knowledge.embeddings import build_or_load_embedding_index
    from job_automation.logging import configure_logging, get_logger

    configure_logging()
    logger = get_logger("scripts.build_knowledge_index")

    paths = PathsConfig(profile_dir=args.profile_dir)
    graph = load_knowledge_graph(paths, with_embeddings=False)
    logger.info("build_start", extra={"atoms": len(graph)})

    if not len(graph):
        logger.error("no_atoms_found")
        return 1

    index = build_or_load_embedding_index(graph.experiences, paths.profile_dir / "faiss")
    if index is None:
        logger.error("index_build_failed")
        return 2

    logger.info(
        "build_done",
        extra={"atoms": len(graph), "index_size": len(index.ids)},
    )
    print(f"Built FAISS index for {len(graph)} atoms → {paths.profile_dir / 'faiss'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())