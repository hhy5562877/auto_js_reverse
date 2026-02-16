from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .browser_connector import BrowserConnector
from .embedding_service import EmbeddingService
from .index_manager import IndexManager
from .node_bridge import NodeBridge

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: dict[str, Any], base_dir: Path):
        self._config = config
        self._base_dir = base_dir
        storage_cfg = config.get("storage", {})
        self._storage_dir = base_dir / storage_cfg.get("base_dir", "storage/archives")
        self._db_dir = str(base_dir / storage_cfg.get("db_dir", "storage/db"))

        cdp_cfg = config.get("chrome_cdp", {})
        chrome_data_dir = cdp_cfg.get("user_data_dir")
        if chrome_data_dir:
            chrome_data_dir = str(base_dir / chrome_data_dir)
        self._browser = BrowserConnector(
            host=cdp_cfg.get("host", "localhost"),
            port=cdp_cfg.get("port", 9222),
            reconnect_interval=cdp_cfg.get("reconnect_interval_sec", 5),
            max_reconnect=cdp_cfg.get("max_reconnect_attempts", 3),
            auto_launch=cdp_cfg.get("auto_launch", True),
            headless=cdp_cfg.get("headless", False),
            user_data_dir=chrome_data_dir,
        )

        node_cfg = config.get("node_worker", {})
        worker_script = str(
            base_dir
            / node_cfg.get(
                "script_path", "src/browser_insight/node_worker/processor.js"
            )
        )
        self._node_bridge = NodeBridge(
            worker_script=worker_script,
            max_old_space_size_mb=node_cfg.get("max_old_space_size_mb", 256),
        )

        emb_cfg = config.get("embedding", {})
        self._embedding = EmbeddingService(
            model_name=emb_cfg.get("model_name", "BAAI/bge-m3"),
            batch_size=emb_cfg.get("batch_size", 32),
            api_key=emb_cfg.get("api_key"),
            api_url=emb_cfg.get("api_url"),
        )

        self._index = IndexManager(self._db_dir)

        pipeline_cfg = config.get("pipeline", {})
        self._max_concurrent = pipeline_cfg.get("max_concurrent_downloads", 5)
        self._max_file_size = pipeline_cfg.get("max_file_size_bytes", 5 * 1024 * 1024)

    @property
    def index(self) -> IndexManager:
        return self._index

    @property
    def embedding(self) -> EmbeddingService:
        return self._embedding

    async def capture_page(
        self,
        force_refresh: bool = False,
        storage_path: Optional[str] = None,
        target_url: Optional[str] = None,
    ) -> dict[str, Any]:
        await self._browser.connect(target_url=target_url)
        current_url = await self._browser.get_current_url()
        domain = BrowserConnector.extract_domain(current_url)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if storage_path:
            base_storage = Path(storage_path)
        else:
            base_storage = self._storage_dir

        session_dir = base_storage / timestamp / domain
        session_dir.mkdir(parents=True, exist_ok=True)

        html = await self._browser.get_document_html()
        (session_dir / "index.html").write_text(html, encoding="utf-8")

        scripts = await self._browser.get_all_scripts()
        logger.info("发现 %d 个脚本标签 (域名: %s)", len(scripts), domain)

        semaphore = asyncio.Semaphore(self._max_concurrent)
        stats = {
            "new_files": 0,
            "skipped": 0,
            "source_maps": 0,
            "chunks_indexed": 0,
            "storage_path": str(session_dir),
        }

        tasks_to_parse: list[dict[str, str]] = []

        def _url_to_local_path(src_url: str) -> Path:
            parsed = urlparse(src_url)
            url_path = parsed.path.lstrip("/")
            if not url_path:
                url_path = "index.js"
            return session_dir / url_path

        async def process_script(script_info: dict) -> None:
            src_url = script_info.get("src", "")
            if not src_url:
                return

            async with semaphore:
                content = await self._browser.download_resource(src_url)
                if not content:
                    return

                file_hash = BrowserConnector.compute_hash(content)

                if not force_refresh and self._index.hash_exists(src_url, file_hash):
                    stats["skipped"] += 1
                    logger.debug("跳过已索引文件: %s", src_url)
                    return

                if len(content) > self._max_file_size:
                    logger.warning(
                        "超大文件 (%d bytes), 将使用行切分: %s", len(content), src_url
                    )

                local_path = _url_to_local_path(src_url)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content)

                map_path: Optional[str] = None
                map_url = src_url + ".map"
                map_content = await self._browser.download_resource(map_url)
                if map_content:
                    map_local = local_path.with_suffix(".js.map")
                    map_local.write_bytes(map_content)
                    map_path = str(map_local)
                    stats["source_maps"] += 1

                self._index.add_file_record(
                    {
                        "url": src_url,
                        "hash": file_hash,
                        "domain": domain,
                        "local_path": str(local_path),
                        "map_path": map_path or "",
                        "source_map_restored": map_path is not None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

                tasks_to_parse.append(
                    {
                        "path": str(local_path),
                        "mapPath": map_path or "",
                        "url": src_url,
                    }
                )
                stats["new_files"] += 1

        await asyncio.gather(*[process_script(s) for s in scripts])

        if tasks_to_parse:
            chunks_indexed = await self._parse_and_index(tasks_to_parse, domain)
            stats["chunks_indexed"] = chunks_indexed

        await self._browser.disconnect()

        metadata = {
            "url": current_url,
            "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "storage_path": str(session_dir),
            "stats": stats,
        }

        (session_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return stats

    async def _parse_and_index(self, files: list[dict[str, str]], domain: str) -> int:
        await self._node_bridge.start()
        result = await self._node_bridge.parse_files(files)

        if result.get("status") != "success":
            logger.error("Node.js 解析失败: %s", result.get("message", "unknown"))
            return 0

        all_texts: list[str] = []
        all_metadata: list[dict] = []

        for file_result in result.get("results", []):
            url = file_result.get("url", "")
            file_hash = ""
            for f in files:
                if f["url"] == url:
                    file_hash = Path(f["path"]).stem
                    break

            for sub_result in file_result.get("results", []):
                original_file = sub_result.get("originalFile", "")
                is_restored = sub_result.get("sourceMapRestored", False)

                for chunk in sub_result.get("chunks", []):
                    text = chunk.get("content", "").strip()
                    if not text or len(text) < 20:
                        continue

                    all_texts.append(text)
                    all_metadata.append(
                        {
                            "original_file": original_file,
                            "url": url,
                            "domain": domain,
                            "line_start": chunk.get("lineStart", 0),
                            "line_end": chunk.get("lineEnd", 0),
                            "source_map_restored": is_restored,
                            "file_hash": file_hash,
                        }
                    )

        if not all_texts:
            return 0

        embeddings = await self._embedding.embed_texts(all_texts)

        db_records = []
        for i, (text, meta, vector) in enumerate(
            zip(all_texts, all_metadata, embeddings)
        ):
            db_records.append(
                {
                    "vector": vector,
                    "text": text,
                    **meta,
                }
            )

        self._index.add_code_chunks(db_records)
        logger.info("成功索引 %d 个代码块", len(db_records))
        return len(db_records)

    async def search(
        self, query: str, domain_filter: Optional[str] = None, limit: int = 10
    ) -> list[dict]:
        query_vector = await self._embedding.embed_query(query)
        results = self._index.search_vectors(
            query_vector, limit=limit, domain_filter=domain_filter
        )
        return results

    async def shutdown(self) -> None:
        await self._node_bridge.stop()
        await self._browser.disconnect()
        self._browser.shutdown_chrome()
