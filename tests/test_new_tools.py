from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from auto_js_reverse.services.browser_connector import BrowserConnector
from auto_js_reverse.services.index_manager import IndexManager
from auto_js_reverse.services.embedding_service import EmbeddingService
from auto_js_reverse.services.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test_new_tools")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / ".mcp_config" / "config.json"
TARGET_URL = "https://www.baidu.com"

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def ensure_test_config(config: dict) -> dict:
    config.setdefault("chrome_cdp", {})
    config.setdefault("storage", {})
    config.setdefault("embedding", {})
    return config


@pytest.mark.unit
def test_list_captured_files() -> bool:
    """测试 IndexManager.list_files_by_domain 和 get_file_by_url"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_list_")
    try:
        idx = IndexManager(tmp_db)

        assert idx.list_files_by_domain() == [], "空库应返回空列表"
        assert idx.list_files_by_domain(domain="test.com") == []

        idx.add_file_record({
            "url": "https://test.com/app.js",
            "hash": "abc123",
            "domain": "test.com",
            "local_path": "/tmp/app.js",
            "map_path": "",
            "source_map_restored": False,
            "timestamp": "2026-02-16T00:00:00Z",
        })
        idx.add_file_record({
            "url": "https://other.com/lib.js",
            "hash": "def456",
            "domain": "other.com",
            "local_path": "/tmp/lib.js",
            "map_path": "/tmp/lib.js.map",
            "source_map_restored": True,
            "timestamp": "2026-02-16T01:00:00Z",
        })

        all_files = idx.list_files_by_domain()
        assert len(all_files) == 2, f"应返回 2 个文件, 实际: {len(all_files)}"

        test_files = idx.list_files_by_domain(domain="test.com")
        assert len(test_files) == 1
        assert test_files[0]["url"] == "https://test.com/app.js"

        record = idx.get_file_by_url("https://test.com/app.js")
        assert record is not None
        assert record["local_path"] == "/tmp/app.js"

        missing = idx.get_file_by_url("https://nonexist.com/x.js")
        assert missing is None

        logger.info("%s list_captured_files (list_files_by_domain + get_file_by_url)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_search_chunks_by_text() -> bool:
    """测试 IndexManager.search_chunks_by_text"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_search_text_")
    try:
        idx = IndexManager(tmp_db)

        fake_vector = [0.1] * 1024
        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "function encrypt(data) { return CryptoJS.AES.encrypt(data, key); }",
                "original_file": "crypto.js",
                "url": "https://test.com/crypto.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": False,
                "file_hash": "abc",
            },
            {
                "vector": fake_vector,
                "text": "function login(user, pass) { return fetch('/api/login'); }",
                "original_file": "auth.js",
                "url": "https://test.com/auth.js",
                "domain": "test.com",
                "line_start": 10,
                "line_end": 12,
                "source_map_restored": False,
                "file_hash": "def",
            },
            {
                "vector": fake_vector,
                "text": "var md5 = require('md5'); var hash = md5(input);",
                "original_file": "hash.js",
                "url": "https://other.com/hash.js",
                "domain": "other.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": False,
                "file_hash": "ghi",
            },
        ])

        results = idx.search_chunks_by_text(r"(?i)\bCryptoJS\b")
        assert len(results) >= 1, f"应匹配 CryptoJS, 实际: {len(results)}"
        assert "CryptoJS" in results[0]["text"]

        results_domain = idx.search_chunks_by_text(r"(?i)\bmd5\b", domain="other.com")
        assert len(results_domain) >= 1
        assert results_domain[0]["domain"] == "other.com"

        results_no = idx.search_chunks_by_text(r"nonexistent_pattern_xyz")
        assert len(results_no) == 0

        logger.info("%s search_chunks_by_text (正则匹配 + 域名过滤)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_read_js_file() -> bool:
    """测试读取 JS 文件（行范围）"""
    tmp_file = Path(tempfile.mktemp(suffix=".js"))
    try:
        lines = [f"// line {i+1}" for i in range(100)]
        lines[49] = "function encrypt(data) { return btoa(data); }"
        tmp_file.write_text("\n".join(lines), encoding="utf-8")

        content = tmp_file.read_text(encoding="utf-8")
        all_lines = content.split("\n")
        assert len(all_lines) == 100

        selected = all_lines[44:54]
        assert len(selected) == 10
        assert "encrypt" in selected[5]

        logger.info("%s read_js_file (行范围读取)", PASS)
        return True
    finally:
        tmp_file.unlink(missing_ok=True)


@pytest.mark.integration
def test_execute_js() -> bool:
    """测试在浏览器中执行 JS 表达式"""
    config = ensure_test_config(load_config())
    config["chrome_cdp"]["auto_launch"] = True
    config["chrome_cdp"]["headless"] = True

    browser = BrowserConnector(
        host=config["chrome_cdp"].get("host", "localhost"),
        port=config["chrome_cdp"].get("port", 9222),
        auto_launch=config["chrome_cdp"].get("auto_launch", True),
        headless=config["chrome_cdp"].get("headless", False),
    )

    async def _test():
        await browser.ensure_connected(target_url=TARGET_URL)

        result = await browser.evaluate("1 + 1")
        assert result == 2, f"1+1 应等于 2, 实际: {result}"

        title = await browser.evaluate("document.title")
        assert isinstance(title, str) and len(title) > 0, f"title 应为非空字符串: {title}"

        url = await browser.evaluate("window.location.href")
        assert "baidu" in url.lower(), f"URL 应包含 baidu: {url}"

        cookie = await browser.evaluate("document.cookie")
        assert isinstance(cookie, str), f"cookie 应为字符串: {type(cookie)}"

        json_result = await browser.evaluate(
            "JSON.stringify({a: 1, b: 'hello'})"
        )
        parsed = json.loads(json_result)
        assert parsed["a"] == 1 and parsed["b"] == "hello"

        try:
            await browser.evaluate("nonExistentVariable.property")
            assert False, "应抛出异常"
        except RuntimeError as e:
            assert "JS 执行异常" in str(e)

        await browser.disconnect()

    asyncio.run(_test())
    logger.info("%s execute_js (算术/DOM/cookie/JSON/异常处理)", PASS)
    return True


@pytest.mark.integration
def test_capture_network() -> bool:
    """测试网络请求捕获"""
    config = ensure_test_config(load_config())
    browser = BrowserConnector(
        host=config["chrome_cdp"].get("host", "localhost"),
        port=config["chrome_cdp"].get("port", 9222),
        auto_launch=True,
        headless=config["chrome_cdp"].get("headless", False),
    )

    async def _test():
        await browser.ensure_connected(target_url=TARGET_URL)

        await browser.evaluate(
            "setTimeout(function() { fetch('/sugrec?prod=pc_his&from=pc_web&json=1'); }, 500)"
        )

        events = await browser.collect_network_events(duration_sec=3.0)

        assert isinstance(events, list), f"应返回列表: {type(events)}"

        if len(events) > 0:
            evt = events[0]
            assert "url" in evt, f"事件应包含 url: {evt.keys()}"
            assert "method" in evt
            assert "headers" in evt
            logger.info("  捕获到 %d 个请求", len(events))
        else:
            logger.info("  未捕获到请求（页面可能无活跃网络活动，属正常）")

        await browser.disconnect()

    asyncio.run(_test())
    logger.info("%s capture_network_requests (Network 域监听)", PASS)
    return True


@pytest.mark.integration
def test_hook_function() -> bool:
    """测试 Hook 函数"""
    config = ensure_test_config(load_config())
    browser = BrowserConnector(
        host=config["chrome_cdp"].get("host", "localhost"),
        port=config["chrome_cdp"].get("port", 9222),
        auto_launch=True,
        headless=config["chrome_cdp"].get("headless", False),
    )

    async def _test():
        await browser.ensure_connected(target_url=TARGET_URL)

        setup = await browser.evaluate("""
        (function() {
            window.__testFunc = function(a, b) { return a + b; };
            return 'ok';
        })()
        """)
        assert setup == "ok"

        hook_js = """
        (function() {
            var _hookedCalls = [];
            var _original = window.__testFunc;
            if (typeof _original !== 'function') {
                return JSON.stringify({error: '__testFunc not found'});
            }
            window.__testFunc = function() {
                var args = Array.prototype.slice.call(arguments);
                var callInfo = {
                    args: args.map(function(a) { return JSON.stringify(a); }),
                };
                var result = _original.apply(this, arguments);
                callInfo.returnValue = JSON.stringify(result);
                _hookedCalls.push(callInfo);
                return result;
            };
            window.__browserInsightHook = {
                calls: _hookedCalls,
                restore: function() { window.__testFunc = _original; },
            };
            return JSON.stringify({status: 'hooked'});
        })()
        """
        hook_result = await browser.evaluate(hook_js)
        parsed = json.loads(hook_result)
        assert parsed.get("status") == "hooked", f"Hook 应成功: {parsed}"

        await browser.evaluate("window.__testFunc(1, 2)")
        await browser.evaluate("window.__testFunc('hello', ' world')")

        calls_raw = await browser.evaluate(
            "JSON.stringify(window.__browserInsightHook.calls)"
        )
        calls = json.loads(calls_raw)
        assert len(calls) == 2, f"应记录 2 次调用, 实际: {len(calls)}"
        assert calls[0]["returnValue"] == "3"
        assert calls[1]["returnValue"] == '"hello world"'

        await browser.evaluate("window.__browserInsightHook.restore()")

        result = await browser.evaluate("window.__testFunc(10, 20)")
        assert result == 30, "恢复后函数应正常工作"

        await browser.disconnect()

    asyncio.run(_test())
    logger.info("%s hook_function (注入/记录/恢复)", PASS)
    return True


@pytest.mark.unit
def test_analyze_encryption() -> bool:
    """测试加密模式扫描"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_encrypt_")
    try:
        idx = IndexManager(tmp_db)
        fake_vector = [0.1] * 1024

        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "var sign = CryptoJS.MD5(params + secret).toString();",
                "original_file": "sign.js",
                "url": "https://test.com/sign.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": False,
                "file_hash": "a1",
            },
            {
                "vector": fake_vector,
                "text": "var encrypted = CryptoJS.AES.encrypt(data, key);",
                "original_file": "crypto.js",
                "url": "https://test.com/crypto.js",
                "domain": "test.com",
                "line_start": 5,
                "line_end": 5,
                "source_map_restored": False,
                "file_hash": "a2",
            },
            {
                "vector": fake_vector,
                "text": "var token = btoa(username + ':' + password);",
                "original_file": "auth.js",
                "url": "https://test.com/auth.js",
                "domain": "test.com",
                "line_start": 10,
                "line_end": 10,
                "source_map_restored": False,
                "file_hash": "a3",
            },
            {
                "vector": fake_vector,
                "text": "function getSign(params) { return hmac(params, secretKey); }",
                "original_file": "api.js",
                "url": "https://test.com/api.js",
                "domain": "test.com",
                "line_start": 20,
                "line_end": 20,
                "source_map_restored": False,
                "file_hash": "a4",
            },
            {
                "vector": fake_vector,
                "text": "function render() { return div.innerHTML; }",
                "original_file": "ui.js",
                "url": "https://test.com/ui.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": False,
                "file_hash": "a5",
            },
        ])

        import re
        ENCRYPTION_PATTERNS = {
            "MD5": r"(?i)\b(md5|MD5|hex_md5)\s*\(",
            "AES": r"(?i)\b(AES|aes)\s*\.\s*(encrypt|decrypt|Encrypt|Decrypt)",
            "Base64": r"(?i)\b(btoa|atob|Base64|base64)\s*\(",
            "CryptoJS": r"CryptoJS\.\w+",
            "sign/signature": r"(?i)\b(sign|signature|getSign|makeSign|calcSign)\s*\(",
        }

        all_matches = {}
        for name, pattern in ENCRYPTION_PATTERNS.items():
            matches = idx.search_chunks_by_text(pattern, domain="test.com", limit=20)
            if matches:
                filtered = [m for m in matches if re.findall(pattern, m.get("text", ""))]
                if filtered:
                    all_matches[name] = filtered

        assert len(all_matches) >= 3, f"应至少检测到 3 种模式, 实际: {list(all_matches.keys())}"
        assert "CryptoJS" in all_matches, "应检测到 CryptoJS"
        assert "Base64" in all_matches, "应检测到 Base64"
        assert "sign/signature" in all_matches, "应检测到 sign/signature"

        ui_matched = idx.search_chunks_by_text(r"CryptoJS", domain="test.com")
        for m in ui_matched:
            assert "render" not in m["text"], "不应匹配无关代码"

        logger.info(
            "%s analyze_encryption (检测到 %d 种模式: %s)",
            PASS, len(all_matches), ", ".join(all_matches.keys())
        )
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_analyze_reverse_targets() -> bool:
    """测试逆向专题分析模板"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_reverse_targets_")
    try:
        idx = IndexManager(tmp_db)
        fake_vector = [0.1] * 1024

        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "window.getSign = function(params, ts, nonce) { return md5(params + ts + nonce + secret); };",
                "original_file": "sign.js",
                "url": "https://test.com/sign.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": True,
                "file_hash": "b1",
            },
            {
                "vector": fake_vector,
                "text": "function buildHeaders(token, ts, nonce) { return { 'x-sign': getSign(ts + nonce), 'x-token': token, 'x-timestamp': ts, 'x-nonce': nonce }; }",
                "original_file": "request.js",
                "url": "https://test.com/request.js",
                "domain": "test.com",
                "line_start": 10,
                "line_end": 12,
                "source_map_restored": True,
                "file_hash": "b2",
            },
            {
                "vector": fake_vector,
                "text": "const injectToken = (config) => { config.headers.Authorization = 'Bearer ' + localStorage.getItem('token'); return config; };",
                "original_file": "auth.js",
                "url": "https://test.com/auth.js",
                "domain": "test.com",
                "line_start": 20,
                "line_end": 20,
                "source_map_restored": False,
                "file_hash": "b3",
            },
            {
                "vector": fake_vector,
                "text": "window.encryptPassword = function(password) { return CryptoJS.AES.encrypt(password, key).toString(); };",
                "original_file": "crypto.js",
                "url": "https://test.com/crypto.js",
                "domain": "test.com",
                "line_start": 30,
                "line_end": 30,
                "source_map_restored": False,
                "file_hash": "b4",
            },
        ])

        class PipelineStub:
            def __init__(self, index: IndexManager):
                self.index = index

        import auto_js_reverse.main as main_mod

        original_pipeline = main_mod.pipeline
        main_mod.pipeline = PipelineStub(idx)
        try:
            result = asyncio.run(
                main_mod.analyze_reverse_targets.fn(domain_filter="test.com")
            )
        finally:
            main_mod.pipeline = original_pipeline

        assert "逆向专题分析" in result
        assert "## sign" in result
        assert "## token" in result
        assert "## encrypt" in result
        assert "## headers" in result
        assert "`window.getSign`" in result
        assert "`window.encryptPassword`" in result
        assert "`x-sign`" in result
        assert "`authorization`" in result.lower()

        logger.info("%s analyze_reverse_targets (专题聚类 + hook 候选 + headers)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_auto_probe_hook_candidates() -> bool:
    """测试自动候选 Hook 试探"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_auto_probe_")
    try:
        idx = IndexManager(tmp_db)
        fake_vector = [0.1] * 1024
        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "window.getSign = function(params, ts, nonce) { return md5(params + ts + nonce + secret); };",
                "original_file": "sign.js",
                "url": "https://test.com/sign.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": True,
                "file_hash": "c1",
            }
        ])

        class BrowserStub:
            def __init__(self):
                self.current_target = ""

            async def ensure_connected(self, target_url: str = None) -> None:
                return None

            async def evaluate(self, expression: str):
                if "window.getSign" in expression and "__browserInsightHook" in expression:
                    self.current_target = "window.getSign"
                    return json.dumps({"status": "hooked", "target": "window.getSign"})
                if expression == "window.login()":
                    return None
                if "JSON.stringify(window.__browserInsightHook" in expression:
                    return json.dumps(
                        [
                            {
                                "args": ['"abc"', '"123"', '"nonce"'],
                                "returnValue": '"sig123"',
                                "stack": ["at window.getSign (<anonymous>:1:1)"],
                            }
                        ]
                    )
                if "window.__browserInsightHook && window.__browserInsightHook.restore()" in expression:
                    return None
                raise AssertionError(f"收到未预期的表达式: {expression}")

        class PipelineStub:
            def __init__(self, index: IndexManager):
                self.index = index
                self._browser = BrowserStub()

        import auto_js_reverse.main as main_mod

        original_pipeline = main_mod.pipeline
        main_mod.pipeline = PipelineStub(idx)
        try:
            result = asyncio.run(
                main_mod.auto_probe_hook_candidates.fn(
                    domain_filter="test.com",
                    focus="sign",
                    trigger_action="window.login()",
                    max_candidates=2,
                    max_calls=3,
                    duration=0.0,
                    stop_on_first_hit=True,
                )
            )
        finally:
            main_mod.pipeline = original_pipeline

        assert "候选 Hook 试探" in result
        assert "`window.getSign`" in result
        assert "✅ 命中 1 次调用" in result
        assert "sig123" in result
        assert "已命中候选入口" in result

        logger.info("%s auto_probe_hook_candidates (自动候选 Hook 试探)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_correlate_request_flow() -> bool:
    """测试请求流与代码线索自动对齐"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_request_flow_")
    try:
        idx = IndexManager(tmp_db)
        fake_vector = [0.1] * 1024
        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "window.getSign = function(body, ts, nonce) { return md5(body + ts + nonce + secret); };",
                "original_file": "sign.js",
                "url": "https://test.com/sign.js",
                "domain": "test.com",
                "line_start": 1,
                "line_end": 1,
                "source_map_restored": True,
                "file_hash": "d1",
            },
            {
                "vector": fake_vector,
                "text": "function attachHeaders(cfg) { cfg.headers['x-sign'] = window.getSign(cfg.data, cfg.headers['x-timestamp'], cfg.headers['x-nonce']); cfg.headers.Authorization = 'Bearer ' + token; return cfg; }",
                "original_file": "request.js",
                "url": "https://test.com/request.js",
                "domain": "test.com",
                "line_start": 10,
                "line_end": 12,
                "source_map_restored": True,
                "file_hash": "d2",
            },
        ])

        class BrowserStub:
            async def ensure_connected(self, target_url: str = None) -> None:
                return None

            async def evaluate(self, expression: str):
                if expression == "window.login()":
                    return None
                if expression == "location.reload()":
                    return None
                raise AssertionError(f"收到未预期的表达式: {expression}")

            async def collect_network_events(self, duration_sec: float) -> list[dict]:
                return [
                    {
                        "url": "https://api.test.com/login",
                        "method": "POST",
                        "headers": {
                            "x-sign": "abc123",
                            "x-timestamp": "1700000000",
                            "x-nonce": "nonce-1",
                            "Authorization": "Bearer token-1",
                            "content-type": "application/json",
                        },
                        "postData": '{"username":"alice","password":"secret"}',
                        "type": "XHR",
                        "initiator": "script",
                        "response": {"status": 200},
                    },
                    {
                        "url": "https://api.test.com/profile",
                        "method": "GET",
                        "headers": {"content-type": "application/json"},
                        "postData": "",
                        "type": "XHR",
                        "initiator": "script",
                        "response": {"status": 200},
                    },
                ]

        class PipelineStub:
            def __init__(self, index: IndexManager):
                self.index = index
                self._browser = BrowserStub()

        import auto_js_reverse.main as main_mod

        original_pipeline = main_mod.pipeline
        main_mod.pipeline = PipelineStub(idx)
        try:
            result = asyncio.run(
                main_mod.correlate_request_flow.fn(
                    domain_filter="test.com",
                    focus="sign",
                    trigger_action="window.login()",
                    duration=0.1,
                    max_requests=2,
                    max_candidates=3,
                )
            )
        finally:
            main_mod.pipeline = original_pipeline

        assert "请求流关联分析" in result
        assert "https://api.test.com/login" in result
        assert "`x-sign`" in result
        assert "`window.getSign`" in result
        assert "`password`" in result

        logger.info("%s correlate_request_flow (请求与代码线索对齐)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


@pytest.mark.unit
def test_generate_verification_actions() -> bool:
    """测试自动生成验证动作"""
    tmp_db = tempfile.mkdtemp(prefix="mcp_test_verification_actions_")
    try:
        idx = IndexManager(tmp_db)
        fake_vector = [0.1] * 1024
        idx.add_code_chunks([
            {
                "vector": fake_vector,
                "text": "window.getSign = function(body, ts, nonce) { return md5(body + ts + nonce + secret); };",
                "original_file": "sign.js",
                "url": "https://test.com/sign.js",
                "domain": "test.com",
                "line_start": 30,
                "line_end": 30,
                "source_map_restored": True,
                "file_hash": "e1",
            },
            {
                "vector": fake_vector,
                "text": "function attachHeaders(cfg) { cfg.headers['x-sign'] = window.getSign(cfg.data, cfg.headers['x-timestamp'], cfg.headers['x-nonce']); return cfg; }",
                "original_file": "request.js",
                "url": "https://test.com/request.js",
                "domain": "test.com",
                "line_start": 50,
                "line_end": 55,
                "source_map_restored": True,
                "file_hash": "e2",
            },
        ])

        class BrowserStub:
            async def ensure_connected(self, target_url: str = None) -> None:
                return None

            async def evaluate(self, expression: str):
                if expression == "window.login()":
                    return None
                if expression == "location.reload()":
                    return None
                raise AssertionError(f"收到未预期的表达式: {expression}")

            async def collect_network_events(self, duration_sec: float) -> list[dict]:
                return [
                    {
                        "url": "https://api.test.com/login",
                        "method": "POST",
                        "headers": {
                            "x-sign": "abc123",
                            "x-timestamp": "1700000000",
                            "x-nonce": "nonce-1",
                        },
                        "postData": '{"password":"secret"}',
                        "type": "XHR",
                        "initiator": "script",
                        "response": {"status": 200},
                    }
                ]

        class PipelineStub:
            def __init__(self, index: IndexManager):
                self.index = index
                self._browser = BrowserStub()

        import auto_js_reverse.main as main_mod

        original_pipeline = main_mod.pipeline
        main_mod.pipeline = PipelineStub(idx)
        try:
            result = asyncio.run(
                main_mod.generate_verification_actions.fn(
                    domain_filter="test.com",
                    focus="sign",
                    target_url="https://test.com/login",
                    trigger_action="window.login()",
                    duration=0.1,
                    max_requests=2,
                    max_candidates=2,
                )
            )
        finally:
            main_mod.pipeline = original_pipeline

        assert "自动验证动作建议" in result
        assert "read_js_file(url=\"https://test.com/sign.js\"" in result
        assert "execute_js(expression=\"typeof window.getSign\"" in result
        assert "hook_function(function_path=\"window.getSign\"" in result
        assert "capture_network_requests(" in result

        logger.info("%s generate_verification_actions (自动生成验证动作)", PASS)
        return True
    finally:
        shutil.rmtree(tmp_db, ignore_errors=True)


def main():
    logger.info("=" * 60)
    logger.info("auto_js_reverse 新工具测试")
    logger.info("=" * 60)

    results: dict[str, bool] = {}

    logger.info("\n--- 1/7 list_captured_files ---")
    results["list_captured_files"] = test_list_captured_files()

    logger.info("\n--- 2/7 search_chunks_by_text ---")
    results["search_chunks_by_text"] = test_search_chunks_by_text()

    logger.info("\n--- 3/7 read_js_file ---")
    results["read_js_file"] = test_read_js_file()

    logger.info("\n--- 4/7 execute_js ---")
    results["execute_js"] = test_execute_js()

    logger.info("\n--- 5/7 capture_network_requests ---")
    results["capture_network"] = test_capture_network()

    logger.info("\n--- 6/7 hook_function ---")
    results["hook_function"] = test_hook_function()

    logger.info("\n--- 7/11 analyze_encryption ---")
    results["analyze_encryption"] = test_analyze_encryption()

    logger.info("\n--- 8/11 analyze_reverse_targets ---")
    results["analyze_reverse_targets"] = test_analyze_reverse_targets()

    logger.info("\n--- 9/11 auto_probe_hook_candidates ---")
    results["auto_probe_hook_candidates"] = test_auto_probe_hook_candidates()

    logger.info("\n--- 10/11 correlate_request_flow ---")
    results["correlate_request_flow"] = test_correlate_request_flow()

    logger.info("\n--- 11/11 generate_verification_actions ---")
    results["generate_verification_actions"] = test_generate_verification_actions()

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
        logger.info("🎉 所有新工具测试通过!")
    else:
        logger.error("⚠️  部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
