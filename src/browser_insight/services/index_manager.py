from __future__ import annotations

import logging
from typing import Optional

import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)

FILE_INDEX_SCHEMA = pa.schema(
    [
        pa.field("url", pa.utf8()),
        pa.field("hash", pa.utf8()),
        pa.field("domain", pa.utf8()),
        pa.field("local_path", pa.utf8()),
        pa.field("map_path", pa.utf8()),
        pa.field("source_map_restored", pa.bool_()),
        pa.field("timestamp", pa.utf8()),
    ]
)

CODE_CHUNKS_SCHEMA = pa.schema(
    [
        pa.field("vector", pa.list_(pa.float32(), 1024)),
        pa.field("text", pa.utf8()),
        pa.field("original_file", pa.utf8()),
        pa.field("url", pa.utf8()),
        pa.field("domain", pa.utf8()),
        pa.field("line_start", pa.int32()),
        pa.field("line_end", pa.int32()),
        pa.field("source_map_restored", pa.bool_()),
        pa.field("file_hash", pa.utf8()),
    ]
)


class IndexManager:
    def __init__(self, db_dir: str):
        self._db = lancedb.connect(db_dir)
        self._file_index: Optional[lancedb.table.Table] = None
        self._code_chunks: Optional[lancedb.table.Table] = None
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        existing = self._db.table_names()

        if "file_index" in existing:
            self._file_index = self._db.open_table("file_index")
        else:
            self._file_index = self._db.create_table(
                "file_index",
                schema=FILE_INDEX_SCHEMA,
            )

        if "code_chunks" in existing:
            self._code_chunks = self._db.open_table("code_chunks")
        else:
            self._code_chunks = self._db.create_table(
                "code_chunks",
                schema=CODE_CHUNKS_SCHEMA,
            )

    def hash_exists(self, url: str, file_hash: str) -> bool:
        try:
            results = (
                self._file_index.search()
                .where(f"url = '{url}' AND hash = '{file_hash}'")
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    def add_file_record(self, record: dict) -> None:
        self._file_index.add([record])

    def add_code_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        self._code_chunks.add(chunks)

    def search_vectors(
        self,
        query_vector: list[float],
        limit: int = 10,
        domain_filter: Optional[str] = None,
    ) -> list[dict]:
        search = self._code_chunks.search(query_vector).metric("cosine").limit(limit)
        if domain_filter:
            search = search.where(f"domain = '{domain_filter}'")
        return search.to_list()

    def list_domains(self) -> list[dict]:
        try:
            df = self._file_index.to_pandas()
            if df.empty:
                return []
            grouped = (
                df.groupby("domain")
                .agg(
                    file_count=("url", "count"),
                    latest=("timestamp", "max"),
                )
                .reset_index()
            )
            return grouped.to_dict("records")
        except Exception:
            return []

    def get_file_count(self) -> int:
        try:
            return self._file_index.count_rows()
        except Exception:
            return 0

    def get_chunk_count(self) -> int:
        try:
            return self._code_chunks.count_rows()
        except Exception:
            return 0

    def delete_by_domain(self, domain: str) -> None:
        try:
            self._file_index.delete(f"domain = '{domain}'")
            self._code_chunks.delete(f"domain = '{domain}'")
        except Exception as e:
            logger.warning("删除域名 %s 数据失败: %s", domain, e)
