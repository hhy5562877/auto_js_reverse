from __future__ import annotations

import logging
import warnings
from pathlib import Path
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

    @staticmethod
    def _quote_filter_value(value: str) -> str:
        # DataFusion SQL 字符串字面量需要把单引号转义成两个单引号。
        return "'" + value.replace("'", "''") + "'"

    def _eq_filter(self, field: str, value: str) -> str:
        return f"{field} = {self._quote_filter_value(value)}"

    def hash_exists(self, url: str, file_hash: str) -> bool:
        try:
            expr = f"{self._eq_filter('url', url)} AND {self._eq_filter('hash', file_hash)}"
            results = (
                self._file_index.search()
                .where(expr)
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception as e:
            logger.debug("hash_exists 查询失败 (url=%s): %s", url, e)
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
            search = search.where(self._eq_filter("domain", domain_filter))
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
            expr = self._eq_filter("domain", domain)
            self._file_index.delete(expr)
            self._code_chunks.delete(expr)
        except Exception as e:
            logger.warning("删除域名 %s 数据失败: %s", domain, e)

    def list_files_by_domain(self, domain: Optional[str] = None) -> list[dict]:
        try:
            df = self._file_index.to_pandas()
            if df.empty:
                return []
            if domain:
                df = df[df["domain"] == domain]
            return df.to_dict("records")
        except Exception:
            return []

    def get_file_by_url(self, url: str) -> Optional[dict]:
        try:
            results = self._file_index.search().where(
                self._eq_filter("url", url)
            ).limit(1).to_list()
            return results[0] if results else None
        except Exception as e:
            logger.debug("get_file_by_url 查询失败 (url=%s): %s", url, e)
            return None

    def get_file_by_local_path(self, local_path: str) -> Optional[dict]:
        try:
            results = self._file_index.search().where(
                self._eq_filter("local_path", local_path)
            ).limit(1).to_list()
            if results:
                return results[0]

            target = Path(local_path).expanduser().resolve(strict=False)
            for record in self.list_files_by_domain():
                candidate = record.get("local_path", "")
                if not candidate:
                    continue
                try:
                    if (
                        Path(candidate).expanduser().resolve(strict=False)
                        == target
                    ):
                        return record
                except Exception:
                    continue
            return None
        except Exception as e:
            logger.debug("get_file_by_local_path 查询失败 (path=%s): %s", local_path, e)
            return None

    def search_chunks_by_text(
        self, pattern: str, domain: Optional[str] = None, limit: int = 50
    ) -> list[dict]:
        try:
            df = self._code_chunks.to_pandas()
            if df.empty:
                return []
            if domain:
                df = df[df["domain"] == domain]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                mask = df["text"].str.contains(
                    pattern, case=False, na=False, regex=True
                )
            matched = df[mask].head(limit)
            cols = [c for c in matched.columns if c != "vector"]
            return matched[cols].to_dict("records")
        except Exception:
            return []
