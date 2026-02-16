from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI

logger = logging.getLogger(__name__)

CHROME_PATHS: dict[str, list[str]] = {
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
    "Linux": [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave-browser",
        "microsoft-edge",
    ],
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
}


def _find_chrome_binary() -> Optional[str]:
    system = platform.system()
    candidates = CHROME_PATHS.get(system, [])

    for candidate in candidates:
        if system == "Linux":
            found = shutil.which(candidate)
            if found:
                return found
        else:
            if Path(candidate).exists():
                return candidate

    for name in ("chrome", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found

    return None


def _no_proxy_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "SOCKS_PROXY",
        "socks_proxy",
    ):
        env.pop(key, None)
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"
    return env


class BrowserConnector:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 9222,
        reconnect_interval: float = 5.0,
        max_reconnect: int = 3,
        auto_launch: bool = True,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
    ):
        self._host = host
        self._port = port
        self._reconnect_interval = reconnect_interval
        self._max_reconnect = max_reconnect
        self._auto_launch = auto_launch
        self._headless = headless
        self._user_data_dir = user_data_dir
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._debugger_url: Optional[str] = None
        self._chrome_process: Optional[subprocess.Popen] = None
        self._launched_by_us = False
        self._connected_tab_url: Optional[str] = None
        self._pending_commands: dict[int, asyncio.Future] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None

    async def _start_reader(self) -> None:
        if self._reader_task and not self._reader_task.done():
            return
        self._reader_task = asyncio.create_task(self._ws_reader_loop())

    async def _stop_reader(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._reader_task = None

    async def _ws_reader_loop(self) -> None:
        try:
            while self._ws:
                try:
                    raw = await self._ws.recv()
                except ConnectionClosed:
                    logger.warning("WebSocket 连接已关闭，reader 退出")
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("收到非 JSON 消息，跳过")
                    continue
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending_commands:
                    fut = self._pending_commands[msg_id]
                    if not fut.done():
                        fut.set_result(msg)
                elif "method" in msg:
                    try:
                        self._event_queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            pass

    async def _is_cdp_available(self) -> bool:
        import aiohttp

        url = f"http://{self._host}:{self._port}/json"
        try:
            connector = aiohttp.TCPConnector(force_close=True)
            async with aiohttp.ClientSession(
                connector=connector, trust_env=False
            ) as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def _launch_chrome(self) -> None:
        chrome_bin = _find_chrome_binary()
        if not chrome_bin:
            raise RuntimeError(
                "未找到 Chrome/Chromium 浏览器。请安装 Chrome 或在配置中指定路径。\n"
                "支持的浏览器: Google Chrome, Chromium, Brave, Microsoft Edge"
            )

        args = [
            chrome_bin,
            f"--remote-debugging-port={self._port}",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        if self._headless:
            args.append("--headless=new")

        if self._user_data_dir:
            Path(self._user_data_dir).mkdir(parents=True, exist_ok=True)
            args.append(f"--user-data-dir={self._user_data_dir}")
        else:
            default_data_dir = Path.home() / ".browser_insight" / "chrome_profile"
            default_data_dir.mkdir(parents=True, exist_ok=True)
            args.append(f"--user-data-dir={default_data_dir}")

        args.append("about:blank")

        logger.info("自动启动 Chrome: %s", chrome_bin)
        self._chrome_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_no_proxy_env(),
        )
        self._launched_by_us = True

    async def _fetch_all_tabs(self) -> list[dict]:
        import aiohttp

        url = f"http://{self._host}:{self._port}/json"
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                connector = aiohttp.TCPConnector(force_close=True)
                async with aiohttp.ClientSession(
                    connector=connector, trust_env=False
                ) as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        return await resp.json()
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(1)
        raise ConnectionRefusedError(
            f"无法连接到 Chrome DevTools (http://{self._host}:{self._port}): {last_err}"
        )

    @staticmethod
    def _url_matches_target(page_url: str, target_url: str) -> bool:
        page_parsed = urlparse(page_url or "")
        target_parsed = urlparse(target_url)
        target_domain = target_parsed.netloc.lower()
        target_path = target_parsed.path.rstrip("/")
        page_domain = page_parsed.netloc.lower()
        page_path = page_parsed.path.rstrip("/")

        if target_domain != page_domain:
            return False

        return (
            not target_path
            or target_path == "/"
            or page_path.startswith(target_path)
        )

    def _match_tab(self, tabs: list[dict], target_url: str) -> Optional[dict]:
        target_parsed = urlparse(target_url)
        target_domain = target_parsed.netloc.lower()
        if not target_domain:
            return None

        for tab in tabs:
            if tab.get("type") != "page" or "webSocketDebuggerUrl" not in tab:
                continue
            tab_url = tab.get("url", "")
            if self._url_matches_target(tab_url, target_url):
                return tab

        return None

    async def _ws_connect(self, debugger_url: str) -> None:
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    debugger_url,
                    max_size=50 * 1024 * 1024,
                    additional_headers={"Host": f"{self._host}:{self._port}"},
                    proxy=None,
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            raise ConnectionRefusedError(f"WebSocket 连接超时 (10s): {debugger_url}")
        self._pending_commands.clear()
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        await self._start_reader()

    async def _ensure_cdp_available(self) -> None:
        if await self._is_cdp_available():
            logger.info("检测到已有 Chrome 实例 (端口 %d)", self._port)
            return

        if not self._auto_launch:
            raise ConnectionRefusedError(
                f"未检测到 Chrome 远程调试端口 ({self._port})，且 auto_launch 已关闭。"
            )

        logger.info("未检测到 Chrome 远程调试端口，尝试自动启动...")
        self._launch_chrome()
        for i in range(10):
            await asyncio.sleep(1)
            if await self._is_cdp_available():
                logger.info("Chrome 已就绪 (等待 %d 秒)", i + 1)
                return

        if self._chrome_process:
            self._chrome_process.kill()
            self._chrome_process = None
        raise RuntimeError("Chrome 已启动但 CDP 端口未就绪，请检查端口是否被占用。")

    async def connect(self, target_url: Optional[str] = None) -> None:
        if self._ws:
            await self.disconnect()

        await self._ensure_cdp_available()

        tabs = await self._fetch_all_tabs()
        selected_tab: Optional[dict] = None

        if target_url:
            selected_tab = self._match_tab(tabs, target_url)
            if selected_tab:
                logger.info("复用已有标签页: %s", selected_tab.get("url"))

        if not selected_tab:
            for tab in tabs:
                if tab.get("type") == "page" and "webSocketDebuggerUrl" in tab:
                    selected_tab = tab
                    break

        if not selected_tab or "webSocketDebuggerUrl" not in selected_tab:
            raise RuntimeError("未找到可用的 Chrome 页面标签。")

        self._debugger_url = selected_tab["webSocketDebuggerUrl"]
        self._connected_tab_url = selected_tab.get("url", "")

        available_tabs = [
            t for t in tabs if t.get("type") == "page" and "webSocketDebuggerUrl" in t
        ]
        failed_debugger_urls: set[str] = set()

        for attempt in range(self._max_reconnect):
            try:
                await self._ws_connect(self._debugger_url)
                logger.info(
                    "CDP 连接成功: %s (页面: %s)",
                    self._debugger_url,
                    self._connected_tab_url,
                )
                break
            except (
                ConnectionRefusedError,
                OSError,
                InvalidURI,
                ImportError,
                asyncio.TimeoutError,
            ) as e:
                logger.warning(
                    "CDP WebSocket 连接失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    self._max_reconnect,
                    e,
                )
                if attempt < self._max_reconnect - 1:
                    failed_debugger_urls.add(self._debugger_url)
                    fallback = None
                    for t in available_tabs:
                        candidate_ws_url = t["webSocketDebuggerUrl"]
                        if (
                            candidate_ws_url != self._debugger_url
                            and candidate_ws_url not in failed_debugger_urls
                        ):
                            fallback = t
                            break
                    if fallback is None:
                        # 未失败 tab 已穷尽后，才允许重试历史失败 tab。
                        for t in available_tabs:
                            if t["webSocketDebuggerUrl"] != self._debugger_url:
                                fallback = t
                                break
                    if fallback:
                        logger.info("尝试备选标签页: %s", fallback.get("url", ""))
                        self._debugger_url = fallback["webSocketDebuggerUrl"]
                        self._connected_tab_url = fallback.get("url", "")
                    await asyncio.sleep(self._reconnect_interval)
                else:
                    raise ConnectionRefusedError(
                        f"CDP 连接失败，已重试 {self._max_reconnect} 次: {e}"
                    )

        if target_url and not self._url_matches_target(
            self._connected_tab_url or "", target_url
        ):
            logger.info("当前标签页非目标页面，导航到: %s", target_url)
            await self.navigate(target_url)

    async def navigate(self, url: str, timeout: float = 15.0) -> str:
        await self._send_command("Page.enable")
        self._drain_events()
        await self._send_command("Page.navigate", {"url": url})

        end_time = asyncio.get_event_loop().time() + timeout
        loaded = False
        while asyncio.get_event_loop().time() < end_time:
            remaining = end_time - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=min(remaining, 0.5)
                )
                if event.get("method") == "Page.loadEventFired":
                    loaded = True
                    break
            except asyncio.TimeoutError:
                continue

        if not loaded:
            logger.warning("等待页面加载超时 (%.1fs)，继续执行: %s", timeout, url)

        current = await self.get_current_url()
        logger.info("已导航到: %s", current)
        return current

    def _is_ws_open(self) -> bool:
        if not self._ws:
            return False

        state = getattr(self._ws, "state", None)
        if state is not None:
            state_name = getattr(state, "name", None)
            if isinstance(state_name, str):
                return state_name.upper() == "OPEN"
            state_value = getattr(state, "value", None)
            if isinstance(state_value, int):
                return state_value == 1
            if isinstance(state, int):
                return state == 1

        open_attr = getattr(self._ws, "open", None)
        if isinstance(open_attr, bool):
            return open_attr

        closed_attr = getattr(self._ws, "closed", None)
        if isinstance(closed_attr, bool):
            return not closed_attr

        return True

    @property
    def is_connected(self) -> bool:
        return self._is_ws_open()

    async def _check_ws_alive(self) -> bool:
        """通过发送一个轻量级 CDP 命令检测 WebSocket 是否真正可用。"""
        if not self._is_ws_open():
            return False

        self._msg_id += 1
        cmd_id = self._msg_id
        msg = {
            "id": cmd_id,
            "method": "Runtime.evaluate",
            "params": {"expression": "1"},
        }
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_commands[cmd_id] = future

        try:
            await self._ws.send(json.dumps(msg))
        except asyncio.CancelledError:
            self._pending_commands.pop(cmd_id, None)
            raise
        except Exception:
            self._pending_commands.pop(cmd_id, None)
            return False
        try:
            resp = await asyncio.wait_for(future, timeout=5.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            return False
        finally:
            self._pending_commands.pop(cmd_id, None)

        return isinstance(resp, dict) and "error" not in resp

    async def ensure_connected(self, target_url: Optional[str] = None) -> None:
        if self.is_connected:
            if await self._check_ws_alive():
                if target_url:
                    current_url = await self.get_current_url()
                    self._connected_tab_url = current_url
                    if not self._url_matches_target(current_url, target_url):
                        logger.info("当前连接页面非目标页面，导航到: %s", target_url)
                        current_url = await self.navigate(target_url)
                        self._connected_tab_url = current_url
                return
            logger.warning("CDP 连接健康检查失败，重新连接")
            await self.disconnect()
        await self.connect(target_url=target_url)

    async def _send_command(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict:
        if not self._ws:
            await self.connect()

        self._msg_id += 1
        cmd_id = self._msg_id
        msg = {"id": cmd_id, "method": method}
        if params:
            msg["params"] = params

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_commands[cmd_id] = future

        try:
            await self._ws.send(json.dumps(msg))
        except ConnectionClosed:
            self._pending_commands.pop(cmd_id, None)
            logger.warning("发送 CDP 命令时连接已断开，尝试重连: %s", method)
            await self.connect()
            future = asyncio.get_event_loop().create_future()
            self._pending_commands[cmd_id] = future
            if not self._ws:
                self._pending_commands.pop(cmd_id, None)
                raise RuntimeError("CDP 重连失败")
            await self._ws.send(json.dumps(msg))

        try:
            resp = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending_commands.pop(cmd_id, None)
            raise RuntimeError(f"CDP 命令超时: {method}")
        finally:
            self._pending_commands.pop(cmd_id, None)

        if "error" in resp:
            raise RuntimeError(f"CDP Error: {resp['error']}")
        return resp.get("result", {})

    async def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        await self.ensure_connected()
        result = await self._send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": return_by_value,
                "awaitPromise": True,
                "generatePreview": True,
            },
        )
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            text = exc.get("text", "")
            exception = exc.get("exception", {})
            desc = exception.get("description", text)
            raise RuntimeError(f"JS 执行异常: {desc}")
        return result.get("result", {}).get("value")

    async def enable_network(self) -> None:
        await self.ensure_connected()
        await self._send_command("Network.enable")

    async def disable_network(self) -> None:
        await self.ensure_connected()
        try:
            await self._send_command("Network.disable")
        except Exception:
            pass

    def _drain_events(self) -> list[dict]:
        events = []
        while not self._event_queue.empty():
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    async def collect_network_events(self, duration_sec: float = 10.0) -> list[dict]:
        self._drain_events()
        await self.enable_network()
        requests_map: dict[str, dict] = {}

        end_time = asyncio.get_event_loop().time() + duration_sec
        try:
            while asyncio.get_event_loop().time() < end_time:
                remaining = end_time - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=min(remaining, 0.5)
                    )
                    method = event.get("method", "")

                    if method == "Network.requestWillBeSent":
                        params = event.get("params", {})
                        req_id = params.get("requestId", "")
                        request = params.get("request", {})
                        requests_map[req_id] = {
                            "requestId": req_id,
                            "url": request.get("url", ""),
                            "method": request.get("method", ""),
                            "headers": request.get("headers", {}),
                            "postData": request.get("postData", ""),
                            "type": params.get("type", ""),
                            "initiator": params.get("initiator", {}).get("type", ""),
                            "response": None,
                        }

                    elif method == "Network.responseReceived":
                        params = event.get("params", {})
                        req_id = params.get("requestId", "")
                        response = params.get("response", {})
                        if req_id in requests_map:
                            requests_map[req_id]["response"] = {
                                "status": response.get("status", 0),
                                "statusText": response.get("statusText", ""),
                                "headers": response.get("headers", {}),
                                "mimeType": response.get("mimeType", ""),
                            }

                except asyncio.TimeoutError:
                    continue
        finally:
            await self.disable_network()

        return list(requests_map.values())

    async def get_response_body(self, request_id: str) -> Optional[str]:
        try:
            result = await self._send_command(
                "Network.getResponseBody", {"requestId": request_id}
            )
            return result.get("body", "")
        except Exception:
            return None

    async def disconnect(self) -> None:
        await self._stop_reader()
        if self._ws:
            try:
                await asyncio.wait_for(self._ws.close(), timeout=3.0)
            except Exception:
                pass
            self._ws = None
        for fut in self._pending_commands.values():
            if not fut.done():
                fut.cancel()
        self._pending_commands.clear()

    def shutdown_chrome(self) -> None:
        if self._launched_by_us and self._chrome_process:
            logger.info(
                "关闭由 MCP 启动的 Chrome 进程 (PID: %d)", self._chrome_process.pid
            )
            self._chrome_process.terminate()
            try:
                self._chrome_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_process.kill()
            self._chrome_process = None
            self._launched_by_us = False

    async def get_current_url(self) -> str:
        result = await self._send_command(
            "Runtime.evaluate", {"expression": "window.location.href"}
        )
        return result.get("result", {}).get("value", "")

    async def get_document_html(self) -> str:
        root = await self._send_command("DOM.getDocument", {"depth": -1})
        node_id = root["root"]["nodeId"]
        result = await self._send_command("DOM.getOuterHTML", {"nodeId": node_id})
        return result.get("outerHTML", "")

    async def get_all_scripts(self) -> list[dict[str, str]]:
        result = await self._send_command(
            "Runtime.evaluate",
            {
                "expression": """
            (() => {
                const scripts = Array.from(document.querySelectorAll('script[src]'));
                return JSON.stringify(scripts.map(s => ({
                    src: s.src,
                    type: s.type || 'text/javascript'
                })));
            })()
            """,
                "returnByValue": True,
            },
        )
        raw = result.get("result", {}).get("value", "[]")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    async def download_resource(self, url: str) -> Optional[bytes]:
        try:
            import aiohttp

            connector = aiohttp.TCPConnector(force_close=True)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.debug("下载资源失败 %s: %s", url, e)
        return None

    @staticmethod
    def compute_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def extract_domain(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or "unknown"
