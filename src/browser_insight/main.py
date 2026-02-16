from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .services.pipeline import Pipeline

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / ".mcp_config" / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


config = _load_config()
pipeline = Pipeline(config=config, base_dir=BASE_DIR)

mcp = FastMCP(name="Browser Insight MCP")


@mcp.tool
async def capture_current_page(
    storage_path: str, target_url: Optional[str] = None, force_refresh: bool = False
) -> str:
    """触发一次完整的全量抓取、归档、分析流程。
    抓取 Chrome 页面的所有 JS 资源，进行 Source Map 还原、AST 语义切分、向量化索引。
    所有原始 JS 文件、Source Map 和还原后的源码都会保存到指定的存储路径下。

    如果用户已有浏览器打开了目标网页，会自动复用该标签页；如果没有则新建标签页并导航。
    不指定 target_url 时，使用当前活跃标签页。

    Args:
        storage_path: 文件存储的绝对路径，所有抓取的 JS 文件将归档到此目录下（按日期/域名/原始路径组织）
        target_url: 目标网页 URL，例如 "https://www.baidu.com"。会自动查找已打开的匹配标签页，找不到则新建
        force_refresh: 是否忽略哈希缓存，强制重新解析所有文件
    """
    try:
        stats = await pipeline.capture_page(
            force_refresh=force_refresh,
            storage_path=storage_path,
            target_url=target_url,
        )
    except ConnectionRefusedError as e:
        return f"❌ 连接失败: {e}"
    except Exception as e:
        logger.exception("capture_current_page 异常")
        return f"❌ 抓取失败: {e}"

    parts = []
    parts.append(f"✅ 抓取完成")
    parts.append(f"新增 {stats['new_files']} 个 JS 文件")
    if stats["skipped"] > 0:
        parts.append(f"跳过 {stats['skipped']} 个已索引文件")
    if stats["source_maps"] > 0:
        parts.append(f"还原了 {stats['source_maps']} 个 Source Map")
    parts.append(f"共索引 {stats['chunks_indexed']} 个代码块")
    parts.append(f"存储路径: {stats['storage_path']}")
    return "，".join(parts) + "。"


@mcp.tool
async def search_local_codebase(
    query: str, domain_filter: Optional[str] = None, limit: int = 10
) -> str:
    """RAG 检索本地已索引的浏览器 JS 代码库。

    Args:
        query: 自然语言搜索问题，例如 "用户登录逻辑" 或 "API 请求封装"
        domain_filter: 限制搜索的域名，例如 "example.com"
        limit: 返回结果数量上限
    """
    try:
        results = await pipeline.search(
            query=query, domain_filter=domain_filter, limit=limit
        )
    except Exception as e:
        logger.exception("search_local_codebase 异常")
        return f"❌ 搜索失败: {e}"

    if not results:
        return "未找到相关代码。请先使用 capture_current_page 抓取页面。"

    output_parts = []
    for i, r in enumerate(results, 1):
        source_tag = (
            "🔄 Source Map 还原" if r.get("source_map_restored") else "📦 混淆代码"
        )
        header = (
            f"### 结果 {i} [{source_tag}]\n"
            f"- 文件: `{r.get('original_file', 'unknown')}`\n"
            f"- 来源: `{r.get('url', '')}`\n"
            f"- 行号: {r.get('line_start', '?')}-{r.get('line_end', '?')}\n"
        )
        code = f"```javascript\n{r.get('text', '')}\n```"
        output_parts.append(header + code)

    return "\n\n".join(output_parts)


@mcp.resource("insight://archived-sites")
def list_archived_sites() -> str:
    """列出本地已归档的所有域名和抓取记录。"""
    domains = pipeline.index.list_domains()
    if not domains:
        return "本地暂无归档数据。请先使用 capture_current_page 抓取页面。"

    total_files = pipeline.index.get_file_count()
    total_chunks = pipeline.index.get_chunk_count()

    lines = [f"📊 本地归档概览 (共 {total_files} 个文件, {total_chunks} 个代码块)\n"]
    for d in domains:
        lines.append(
            f"- **{d['domain']}**: {d['file_count']} 个文件, 最近抓取: {d['latest']}"
        )
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
