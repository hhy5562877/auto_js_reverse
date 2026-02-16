from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from browser_insight.services.browser_connector import (
    BrowserConnector,
    _find_chrome_binary,
)
from browser_insight.services.node_bridge import NodeBridge
from browser_insight.services.index_manager import IndexManager
from browser_insight.services.embedding_service import EmbeddingService
from browser_insight.services.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test_e2e")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / ".mcp_config" / "config.json"
TARGET_URL = "https://www.baidu.com"

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def test_chrome_detection() -> bool:
    chrome = _find_chrome_binary()
    if chrome:
        logger.info("%s Chrome 检测: %s", PASS, chrome)
        return True
    logger.error("%s 未找到 Chrome 浏览器", FAIL)
    return False


def test_node_worker() -> bool:
    worker_script = (
        BASE_DIR / "src" / "browser_insight" / "node_worker" / "processor.js"
    )
    if not worker_script.exists():
        logger.error("%s processor.js 不存在", FAIL)
        return False

    node_modules = worker_script.parent / "node_modules"
    if not node_modules.exists():
        logger.error("%s node_modules 未安装", FAIL)
        return False

    async def _test():
        bridge = NodeBridge(str(worker_script))
        await bridge.start()

        result = await bridge.parse_files([])
        assert result["status"] == "success", (
            f"空文件列表应返回 success, 实际: {result}"
        )

        test_file = Path(tempfile.mktemp(suffix=".js"))
        test_file.write_text(
            "function hello() { return 'world'; }\nconst x = 1;", encoding="utf-8"
        )
        try:
            result = await bridge.parse_files(
                [
                    {
                        "path": str(test_file),
                        "mapPath": "",
                        "url": "https://test.com/hello.js",
                    }
                ]
            )
            assert result["status"] == "success"
            chunks = result["results"][0]["results"][0]["chunks"]
            assert len(chunks) > 0, "应至少提取一个代码块"
        finally:
            test_file.unlink(missing_ok=True)
            await bridge.stop()

    asyncio.run(_test())
    logger.info("%s Node.js Worker (ping + AST 解析)", PASS)
    return True


def test_embedding_service() -> bool:
    config = load_config()
    emb_cfg = config.get("embedding", {})
    svc = EmbeddingService(
        model_name=emb_cfg.get("model_name", "BAAI/bge-m3"),
        batch_size=emb_cfg.get("batch_size", 32),
        api_key=emb_cfg.get("api_key"),
        api_url=emb_cfg.get("api_url"),
    )

    async def _test():
        vectors = await svc.embed_texts(["function login() { return token; }"])
        assert len(vectors) == 1, f"应返回 1 个向量, 实际: {len(vectors)}"
        assert len(vectors[0]) == 1024, f"向量维度应为 1024, 实际: {len(vectors[0])}"

        query_vec = await svc.embed_query("login function")
        assert len(query_vec) == 1024

    asyncio.run(_test())
    logger.info("%s Embedding Service (硅基流动 API + 向量化 + 查询向量)", PASS)
    return True


def test_index_manager() -> bool:
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_db_")
    try:
        idx = IndexManager(tmp_db)

        assert idx.get_file_count() == 0
        assert idx.get_chunk_count() == 0

        idx.add_file_record(
            {
                "url": "https://test.com/app.js",
                "hash": "abc123",
                "domain": "test.com",
                "local_path": "/tmp/app.js",
                "map_path": "",
                "source_map_restored": False,
                "timestamp": "2026-02-16T00:00:00Z",
            }
        )
        assert idx.get_file_count() == 1
        assert idx.hash_exists("https://test.com/app.js", "abc123")
        assert not idx.hash_exists("https://test.com/app.js", "xyz789")

        fake_vector = [0.1] * 1024
        idx.add_code_chunks(
            [
                {
                    "vector": fake_vector,
                    "text": "function test() {}",
                    "original_file": "app.js",
                    "url": "https://test.com/app.js",
                    "domain": "test.com",
                    "line_start": 1,
                    "line_end": 1,
                    "source_map_restored": False,
                    "file_hash": "abc123",
                }
            ]
        )
        assert idx.get_chunk_count() == 1

        results = idx.search_vectors(fake_vector, limit=5)
        assert len(results) >= 1

        domains = idx.list_domains()
        assert len(domains) == 1
        assert domains[0]["domain"] == "test.com"

        logger.info("%s IndexManager (CRUD + 哈希去重 + 向量检索)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


def test_full_pipeline_baidu() -> bool:
    config = load_config()
    config["chrome_cdp"]["auto_launch"] = True
    config["chrome_cdp"]["headless"] = True

    tmp_storage = Path(tempfile.mkdtemp(prefix="mcp_test_storage_"))
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_pipeline_db_")
    config["storage"]["db_dir"] = tmp_db

    pipeline = Pipeline(config=config, base_dir=BASE_DIR)
    pipeline._index = IndexManager(tmp_db)

    async def _run():
        stats = await pipeline.capture_page(
            force_refresh=True,
            storage_path=str(tmp_storage),
            target_url=TARGET_URL,
        )

        logger.info("抓取统计: %s", json.dumps(stats, ensure_ascii=False))

        assert stats["new_files"] >= 0, "new_files 应 >= 0"
        storage_path = Path(stats["storage_path"])
        assert storage_path.exists(), f"存储路径应存在: {storage_path}"

        index_html = storage_path / "index.html"
        assert index_html.exists(), "index.html 应存在"
        html_content = index_html.read_text(encoding="utf-8")
        assert len(html_content) > 100, "index.html 内容不应为空"

        metadata_file = storage_path / "metadata.json"
        assert metadata_file.exists(), "metadata.json 应存在"
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        assert "baidu" in metadata["domain"].lower()

        js_files = list(storage_path.rglob("*.js"))
        logger.info("存储的 JS 文件数: %d", len(js_files))
        for f in js_files[:5]:
            rel = f.relative_to(storage_path)
            logger.info("  - %s (%d bytes)", rel, f.stat().st_size)

        if stats["chunks_indexed"] > 0:
            results = await pipeline.search("百度搜索", domain_filter=None, limit=5)
            logger.info("搜索 '百度搜索' 返回 %d 条结果", len(results))
            assert len(results) > 0, "索引后搜索应有结果"

        await pipeline.shutdown()
        return stats

    try:
        stats = asyncio.run(_run())

        logger.info("%s 完整管线测试 (百度)", PASS)
        logger.info("  - 新增文件: %d", stats["new_files"])
        logger.info("  - Source Map: %d", stats["source_maps"])
        logger.info("  - 索引代码块: %d", stats["chunks_indexed"])
        logger.info("  - 存储路径: %s", stats["storage_path"])
        return True
    except Exception as e:
        logger.exception("%s 完整管线测试失败: %s", FAIL, e)
        return False
    finally:
        shutil.rmtree(tmp_storage, ignore_errors=True)
        shutil.rmtree(tmp_db, ignore_errors=True)


def main():
    logger.info("=" * 60)
    logger.info("Browser Insight MCP 端到端测试")
    logger.info("目标: %s", TARGET_URL)
    logger.info("=" * 60)

    results: dict[str, bool] = {}

    logger.info("\n--- 1/5 Chrome 浏览器检测 ---")
    results["chrome_detection"] = test_chrome_detection()

    logger.info("\n--- 2/5 Node.js Worker ---")
    results["node_worker"] = test_node_worker()

    logger.info("\n--- 3/5 Embedding Service ---")
    results["embedding"] = test_embedding_service()

    logger.info("\n--- 4/5 IndexManager ---")
    results["index_manager"] = test_index_manager()

    if all(results.values()):
        logger.info("\n--- 5/5 完整管线 (www.baidu.com) ---")
        results["full_pipeline"] = test_full_pipeline_baidu()
    else:
        logger.warning("\n--- 5/5 跳过完整管线测试 (前置测试未全部通过) ---")
        results["full_pipeline"] = False

    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总:")
    logger.info("=" * 60)
    all_passed = True
    for name, passed in results.items():
        status = PASS if passed else FAIL
        logger.info("  %s %s", status, name)
        if not passed:
            all_passed = False

    logger.info("=" * 60)
    if all_passed:
        logger.info("🎉 所有测试通过!")
    else:
        logger.error("⚠️  部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
