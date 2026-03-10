from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from browser_insight.services.pipeline import Pipeline


pytestmark = pytest.mark.unit


class FakeEmbeddingService:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    async def embed_query(self, query: str) -> list[float]:
        return [0.2] * 1024


class FakeNodeBridge:
    async def start(self) -> None:
        return None

    async def parse_files(self, files: list[dict[str, str]]) -> dict:
        return {
            "status": "success",
            "results": [
                {
                    "url": files[0]["url"],
                    "results": [
                        {
                            "originalFile": "restored.js",
                            "sourceMapRestored": True,
                            "chunks": [
                                {
                                    "content": "function importantFeature() { return 'ok'; }",
                                    "lineStart": 3,
                                    "lineEnd": 5,
                                }
                            ],
                        }
                    ],
                }
            ],
        }


def test_pipeline_init_without_embedding_key() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="pipeline_init_"))
    try:
        config = {
            "storage": {"db_dir": str(tmp_root / "db")},
            "embedding": {},
        }
        pipeline = Pipeline(config=config, base_dir=tmp_root)

        assert pipeline.get_embedding_unavailable_reason() is not None
        assert pipeline.index.get_file_count() == 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_build_session_dir_creates_snapshot_paths() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="pipeline_session_"))
    try:
        pipeline = Pipeline(
            config={"storage": {"db_dir": str(tmp_root / "db")}},
            base_dir=tmp_root,
        )
        captured_at = datetime(2026, 3, 10, 13, 55, 1, 123456, tzinfo=timezone.utc)

        first = pipeline._build_session_dir(tmp_root, "example.com", captured_at)
        second = pipeline._build_session_dir(tmp_root, "example.com", captured_at)

        assert first != second
        assert first.parent == second.parent
        assert first.name.startswith("135501-123456")
        assert second.name.startswith("135501-123456")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_parse_and_index_uses_content_hash() -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="pipeline_index_"))
    try:
        pipeline = Pipeline(
            config={"storage": {"db_dir": str(tmp_root / "db")}},
            base_dir=tmp_root,
        )
        pipeline._embedding = FakeEmbeddingService()
        pipeline._node_bridge = FakeNodeBridge()

        files = [
            {
                "path": str(tmp_root / "app.js"),
                "mapPath": "",
                "url": "https://example.com/app.js",
                "fileHash": "real-content-hash",
            }
        ]

        indexed = asyncio.run(pipeline._parse_and_index(files, "example.com"))
        assert indexed == 1

        results = pipeline.index.search_chunks_by_text("importantFeature", domain="example.com")
        assert len(results) == 1
        assert results[0]["file_hash"] == "real-content-hash"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
