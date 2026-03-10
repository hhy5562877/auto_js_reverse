from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .services.pipeline import Pipeline
from .services.reverse_analyzer import ReverseAnalyzer

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / ".mcp_config" / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


config = _load_config()
pipeline = Pipeline(config=config, base_dir=BASE_DIR)

mcp = FastMCP(name="auto_js_reverse")


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
        storage_path: 文件存储的绝对路径，所有抓取的 JS 文件将归档到此目录下（按日期/域名/会话时间/原始路径组织）
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
    parts.append("✅ 抓取完成")
    parts.append(f"新增 {stats['new_files']} 个 JS 文件")
    if stats["skipped"] > 0:
        parts.append(f"跳过 {stats['skipped']} 个已索引文件")
    if stats["source_maps"] > 0:
        parts.append(f"还原了 {stats['source_maps']} 个 Source Map")
    parts.append(f"共索引 {stats['chunks_indexed']} 个代码块")
    if stats.get("indexing_warning"):
        parts.append(stats["indexing_warning"])
    parts.append(f"存储路径: {stats['storage_path']}")
    return "，".join(parts) + "。"


@mcp.tool
async def search_local_codebase(
    query: str, domain_filter: Optional[str] = None, limit: int = 10
) -> str:
    """RAG 语义检索本地已索引的浏览器 JS 代码库。
    用自然语言描述你要找的功能，返回最相关的代码片段。

    Args:
        query: 自然语言搜索问题，例如 "用户登录逻辑"、"API 请求签名"、"加密函数"
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

    seen_texts: set[str] = set()
    unique_results = []
    for r in results:
        text_key = r.get("text", "")[:200]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_results.append(r)

    output_parts = []
    for i, r in enumerate(unique_results, 1):
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


@mcp.tool
async def list_captured_files(domain_filter: Optional[str] = None) -> str:
    """列出本地已抓取归档的所有 JS 文件。
    可按域名过滤。返回每个文件的 URL、本地路径、是否有 Source Map。
    用于了解当前已抓取了哪些资源，再决定用 read_js_file 读取具体文件。

    Args:
        domain_filter: 限制列出的域名，例如 "www.baidu.com"。不填则列出所有域名
    """
    files = pipeline.index.list_files_by_domain(domain=domain_filter)
    if not files:
        hint = f" (域名: {domain_filter})" if domain_filter else ""
        return f"暂无已抓取的文件{hint}。请先使用 capture_current_page 抓取页面。"

    lines = [f"📁 已抓取文件列表 (共 {len(files)} 个)\n"]
    for f in files:
        sm = "✅ 有 Source Map" if f.get("source_map_restored") else "❌ 无 Source Map"
        local = f.get("local_path", "")
        size = ""
        if local and Path(local).exists():
            size = f" ({Path(local).stat().st_size:,} bytes)"
        lines.append(
            f"- `{f.get('url', '')}`\n"
            f"  本地: `{local}`{size}\n"
            f"  {sm} | 域名: {f.get('domain', '')} | 时间: {f.get('timestamp', '')}"
        )
    return "\n".join(lines)


@mcp.tool
async def read_js_file(
    file_path: Optional[str] = None,
    url: Optional[str] = None,
    start_line: int = 1,
    end_line: Optional[int] = None,
) -> str:
    """读取已抓取的 JS 文件源码。支持通过本地路径或 URL 定位文件。
    可指定行范围只读取部分代码，适合查看大文件的特定区域。

    使用流程: 先用 list_captured_files 查看文件列表，再用本工具读取具体文件。

    Args:
        file_path: JS 文件的本地绝对路径（必须来自 list_captured_files 输出）
        url: JS 文件的原始 URL（二选一，优先使用 file_path）
        start_line: 起始行号（从 1 开始，默认 1）
        end_line: 结束行号（不填则读到文件末尾）
    """
    target_path: Optional[Path] = None

    if start_line <= 0:
        return "❌ start_line 必须大于等于 1。"
    if end_line is not None and end_line <= 0:
        return "❌ end_line 必须大于等于 1。"
    if end_line is not None and end_line < start_line:
        return "❌ end_line 必须大于等于 start_line。"

    if file_path:
        try:
            candidate = Path(file_path).expanduser().resolve(strict=False)
        except Exception as e:
            return f"❌ 文件路径无效: {e}"
        record = pipeline.index.get_file_by_local_path(str(candidate))
        if not record or not record.get("local_path"):
            return (
                "❌ 安全限制：仅允许读取已归档的 JS 文件。\n"
                "请先使用 list_captured_files 获取文件路径，再传入 file_path。"
            )
        target_path = Path(record["local_path"])
    elif url:
        record = pipeline.index.get_file_by_url(url)
        if record and record.get("local_path"):
            target_path = Path(record["local_path"])
        else:
            return f"❌ 未找到 URL 对应的本地文件: {url}\n请先使用 capture_current_page 抓取。"
    else:
        return "❌ 请提供 file_path 或 url 参数。"

    if target_path.suffix.lower() in {".map"}:
        return "❌ 仅支持读取归档的 JS 源文件，不支持 .map 文件。"

    if not target_path.exists():
        return f"❌ 文件不存在: {target_path}"

    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"❌ 读取失败: {e}"

    all_lines = content.split("\n")
    total = len(all_lines)
    if start_line > total:
        return f"❌ start_line 超出文件总行数 ({total})。"

    start = start_line - 1
    end = min(total, end_line) if end_line is not None else total
    selected = all_lines[start:end]

    header = f"📄 `{target_path.name}` (行 {start + 1}-{end}/{total})\n"
    numbered = "\n".join(
        f"{start + 1 + i:>6} | {line}" for i, line in enumerate(selected)
    )
    return header + f"```javascript\n{numbered}\n```"


@mcp.tool
async def execute_js(expression: str, target_url: Optional[str] = None) -> str:
    """在当前浏览器页面上下文中执行 JavaScript 表达式并返回结果。
    用于逆向分析时验证假设、调用页面函数、检查变量值等。

    支持 await 异步表达式。返回值会自动 JSON 序列化。

    Args:
        expression: 要执行的 JS 表达式，例如 "document.cookie" 或 "JSON.stringify(window._config)"
        target_url: 目标页面 URL（可选，不填则使用当前连接的页面）
    """
    try:
        await pipeline._browser.ensure_connected(target_url=target_url)
        result = await pipeline._browser.evaluate(expression)
    except Exception as e:
        return f"❌ 执行失败: {e}"

    if result is None:
        return "执行完成，返回值: undefined"

    if isinstance(result, str):
        return f"```\n{result}\n```"

    try:
        formatted = json.dumps(result, ensure_ascii=False, indent=2)
        return f"```json\n{formatted}\n```"
    except (TypeError, ValueError):
        return f"```\n{result}\n```"


@mcp.tool
async def capture_network_requests(
    target_url: Optional[str] = None,
    duration: float = 10.0,
    trigger_action: Optional[str] = None,
    filter_type: Optional[str] = None,
) -> str:
    """监听浏览器网络请求，捕获指定时间段内的所有 XHR/Fetch/脚本请求。
    这是逆向分析的核心工具——观察页面发出了哪些 API 请求、携带了什么参数和签名。

    使用 trigger_action 参数传入一段 JS 代码，工具会在开始监听后自动执行它来触发网络请求。
    例如传入 "document.querySelector('#submit').click()" 来点击提交按钮。
    如果不传 trigger_action，工具会自动刷新页面来触发请求。

    Args:
        target_url: 目标页面 URL（可选，不填则使用当前页面）
        duration: 监听时长（秒），默认 10 秒
        trigger_action: 监听开始后自动执行的 JS 代码，用于触发网络请求。例如点击按钮、提交表单、调用 fetch 等
        filter_type: 过滤请求类型，可选 "XHR"、"Fetch"、"Script"。不填则捕获所有类型
    """
    try:
        await pipeline._browser.ensure_connected(target_url=target_url)

        async def _trigger():
            await asyncio.sleep(0.3)
            if trigger_action:
                try:
                    await pipeline._browser.evaluate(trigger_action)
                except Exception as e:
                    logger.warning("trigger_action 执行失败: %s", e)
            else:
                try:
                    await pipeline._browser.evaluate("location.reload()")
                except Exception:
                    pass

        asyncio.create_task(_trigger())
        events = await pipeline._browser.collect_network_events(duration_sec=duration)
    except Exception as e:
        return f"❌ 网络监听失败: {e}"

    if filter_type:
        events = [e for e in events if e.get("type", "").lower() == filter_type.lower()]

    if not events:
        return f"在 {duration} 秒内未捕获到网络请求。尝试在页面上触发操作后重新监听。"

    lines = [f"🌐 捕获到 {len(events)} 个网络请求 ({duration}s)\n"]
    for i, evt in enumerate(events, 1):
        resp = evt.get("response") or {}
        status = resp.get("status", "-")
        lines.append(
            f"### 请求 {i}\n"
            f"- **{evt.get('method', '?')}** `{evt.get('url', '')}`\n"
            f"- 类型: {evt.get('type', '?')} | 状态: {status}\n"
            f"- 发起方: {evt.get('initiator', '?')}"
        )
        if evt.get("postData"):
            post = evt["postData"]
            if len(post) > 2000:
                post = post[:2000] + "...(截断)"
            lines.append(f"- POST 数据:\n```\n{post}\n```")

        req_headers = evt.get("headers", {})
        interesting = {
            k: v
            for k, v in req_headers.items()
            if k.lower()
            in (
                "authorization",
                "cookie",
                "x-token",
                "x-sign",
                "x-signature",
                "x-timestamp",
                "x-nonce",
                "content-type",
                "referer",
                "origin",
            )
        }
        if interesting:
            lines.append("- 关键请求头:")
            for k, v in interesting.items():
                lines.append(f"  - `{k}`: `{v}`")

    return "\n".join(lines)


@mcp.tool
async def hook_function(
    function_path: str,
    target_url: Optional[str] = None,
    trigger_action: Optional[str] = None,
    max_calls: int = 10,
    duration: float = 15.0,
) -> str:
    """在页面中 Hook 指定的 JavaScript 函数，记录其调用参数、返回值和调用栈。
    这是逆向分析加密函数的关键工具——找到可疑函数后，用 hook 观察实际的输入输出。

    使用 trigger_action 参数传入一段 JS 代码，工具会在 Hook 注入后自动执行它来触发函数调用。
    例如传入 "document.querySelector('#login-btn').click()" 来触发登录流程。
    如果不传 trigger_action，工具会等待 duration 秒，期间页面自身的操作可能触发函数调用。

    Args:
        function_path: 要 hook 的函数路径，例如 "window.encrypt"、"JSON.stringify"、"CryptoJS.MD5"
        target_url: 目标页面 URL（可选）
        trigger_action: Hook 注入后自动执行的 JS 代码，用于触发目标函数调用
        max_calls: 最多记录多少次调用，默认 10
        duration: 监听时长（秒），默认 15 秒
    """
    safe_path = function_path.replace("'", "\\'")
    hook_js = (
        """
    (function() {
        var _hookedCalls = [];
        var _maxCalls = """
        + str(max_calls)
        + """;
        var _target;
        try { _target = """
        + function_path
        + """; } catch(e) {
            return JSON.stringify({error: '"""
        + safe_path
        + """ 不存在: ' + e.message});
        }
        if (typeof _target !== 'function') {
            return JSON.stringify({error: '"""
        + safe_path
        + """ 不是函数'});
        }
        var _original = _target;
        var _parts = '"""
        + safe_path
        + """'.split('.');
        var _parent = _parts.length > 1
            ? _parts.slice(0, -1).reduce(function(o, k) { return o[k]; }, window)
            : window;
        var _key = _parts[_parts.length - 1];

        _parent[_key] = function() {
            var args = Array.prototype.slice.call(arguments);
            var callInfo = {
                args: args.map(function(a) {
                    try { return JSON.stringify(a).substring(0, 500); }
                    catch(e) { return String(a).substring(0, 500); }
                }),
                stack: new Error().stack.split('\\n').slice(1, 6).map(function(s) { return s.trim(); }),
            };
            var result = _original.apply(this, arguments);
            try { callInfo.returnValue = JSON.stringify(result).substring(0, 500); }
            catch(e) { callInfo.returnValue = String(result).substring(0, 500); }
            if (_hookedCalls.length < _maxCalls) _hookedCalls.push(callInfo);
            return result;
        };

        window.__browserInsightHook = {
            calls: _hookedCalls,
            restore: function() { _parent[_key] = _original; },
        };
        return JSON.stringify({status: 'hooked', target: '"""
        + safe_path
        + """'});
    })()
    """
    )

    try:
        await pipeline._browser.ensure_connected(target_url=target_url)
        hook_result = await pipeline._browser.evaluate(hook_js)
    except Exception as e:
        return f"❌ Hook 失败: {e}"

    parsed = json.loads(hook_result) if isinstance(hook_result, str) else hook_result
    if isinstance(parsed, dict) and parsed.get("error"):
        return f"❌ {parsed['error']}"

    if trigger_action:
        try:
            await pipeline._browser.evaluate(trigger_action)
        except Exception as e:
            logger.warning("trigger_action 执行失败: %s", e)

    await asyncio.sleep(duration)

    try:
        calls_raw = await pipeline._browser.evaluate(
            "JSON.stringify(window.__browserInsightHook ? window.__browserInsightHook.calls : [])"
        )
        await pipeline._browser.evaluate(
            "window.__browserInsightHook && window.__browserInsightHook.restore()"
        )
    except Exception as e:
        return f"❌ 获取 Hook 结果失败: {e}"

    calls = json.loads(calls_raw) if isinstance(calls_raw, str) else calls_raw
    if not calls:
        return (
            f"在 {duration} 秒内 `{function_path}` 未被调用。尝试在页面上触发相关操作。"
        )

    lines = [f"🪝 `{function_path}` 被调用 {len(calls)} 次 ({duration}s)\n"]
    for i, call in enumerate(calls, 1):
        lines.append(f"### 调用 {i}")
        lines.append(f"- 参数: {', '.join(call.get('args', []))}")
        lines.append(f"- 返回值: {call.get('returnValue', 'undefined')}")
        stack = call.get("stack", [])
        if stack:
            lines.append("- 调用栈:")
            for s in stack[:5]:
                lines.append(f"  - `{s}`")

    return "\n".join(lines)


ENCRYPTION_PATTERNS = {
    "MD5": r"(?i)\b(md5|MD5|hex_md5)\s*\(",
    "SHA": r"(?i)\b(sha1|sha256|sha512|SHA)\s*\(",
    "AES": r"(?i)\b(AES|aes)\s*\.\s*(encrypt|decrypt|Encrypt|Decrypt)",
    "DES/3DES": r"(?i)\b(DES|TripleDES|des)\s*\.\s*(encrypt|decrypt)",
    "RSA": r"(?i)\b(RSA|rsa)\s*\.\s*(encrypt|decrypt|sign|verify)",
    "Base64": r"(?i)\b(btoa|atob|Base64|base64)\s*\(",
    "HMAC": r"(?i)\b(hmac|HMAC|HmacSHA|HmacMD5)\s*\(",
    "CryptoJS": r"CryptoJS\.\w+",
    "JSEncrypt": r"JSEncrypt|jsencrypt",
    "sign/signature": r"(?i)\b(sign|signature|getSign|makeSign|calcSign)\s*\(",
    "token/encrypt": r"(?i)\b(encrypt|decrypt|encode|decode|encryptData|decryptData)\s*\(",
}


@mcp.tool
async def analyze_encryption(domain_filter: Optional[str] = None) -> str:
    """扫描已索引的代码库，自动识别常见的加密/签名模式。
    检测 MD5、SHA、AES、RSA、DES、Base64、HMAC、自定义签名函数等。
    返回匹配的代码片段及其位置，帮助快速定位加密逻辑。

    Args:
        domain_filter: 限制扫描的域名，例如 "www.example.com"
    """
    all_matches: dict[str, list[dict]] = {}

    for name, pattern in ENCRYPTION_PATTERNS.items():
        matches = pipeline.index.search_chunks_by_text(
            pattern, domain=domain_filter, limit=20
        )
        if matches:
            filtered = []
            for m in matches:
                text = m.get("text", "")
                found = re.findall(pattern, text)
                if found:
                    filtered.append(m)
            if filtered:
                all_matches[name] = filtered

    if not all_matches:
        return (
            "未检测到常见加密模式。可能使用了自定义混淆或 WASM 加密。\n"
            "建议使用 capture_network_requests 观察 API 请求中的加密参数。"
        )

    lines = ["🔐 加密模式分析结果\n"]
    total = sum(len(v) for v in all_matches.values())
    lines.append(f"共检测到 {total} 处加密相关代码，涉及 {len(all_matches)} 种模式:\n")

    for name, matches in all_matches.items():
        lines.append(f"## {name} ({len(matches)} 处)")
        for m in matches[:5]:
            text = m.get("text", "")
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(
                f"- 文件: `{m.get('original_file', '?')}` "
                f"(行 {m.get('line_start', '?')}-{m.get('line_end', '?')})\n"
                f"```javascript\n{text}\n```"
            )
        if len(matches) > 5:
            lines.append(f"  ...还有 {len(matches) - 5} 处")

    lines.append(
        "\n💡 建议下一步:\n"
        "1. 用 read_js_file 查看完整的加密函数\n"
        "2. 用 hook_function 观察加密函数的实际输入输出\n"
        "3. 用 execute_js 在页面中调用加密函数验证"
    )
    return "\n".join(lines)


@mcp.tool
async def analyze_reverse_targets(
    domain_filter: Optional[str] = None, focus: Optional[str] = None
) -> str:
    """按 sign/token/encrypt/headers 四类专题扫描已索引代码，提炼逆向入口。
    除了返回代码片段，还会输出更适合下一步操作的 Hook 候选函数、关键请求头和推荐搜索词。

    Args:
        domain_filter: 限制扫描的域名，例如 "www.example.com"
        focus: 指定专题，可选 sign、token、encrypt、headers。不填则全部扫描
    """
    try:
        analyzer = ReverseAnalyzer(pipeline.index)
        return analyzer.render_report(domain_filter=domain_filter, focus=focus)
    except ValueError as e:
        return f"❌ 参数错误: {e}"
    except Exception as e:
        logger.exception("analyze_reverse_targets 异常")
        return f"❌ 逆向专题分析失败: {e}"


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
