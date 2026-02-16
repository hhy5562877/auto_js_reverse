from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NodeBridge:
    def __init__(self, worker_script: str, max_old_space_size_mb: int = 256):
        self._worker_script = Path(worker_script).resolve()
        self._max_old_space_size = max_old_space_size_mb
        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._node_path = shutil.which("node")

    def _validate_env(self) -> None:
        if not self._node_path:
            raise RuntimeError("未找到 Node.js。请确保 node 已安装并在 PATH 中。")
        if not self._worker_script.exists():
            raise FileNotFoundError(f"Worker 脚本不存在: {self._worker_script}")

        node_modules = self._worker_script.parent / "node_modules"
        if not node_modules.exists():
            raise RuntimeError(
                f"Node.js 依赖未安装。请执行: cd {self._worker_script.parent} && npm install"
            )

    async def start(self) -> None:
        if self._process and self._process.returncode is None:
            return

        self._validate_env()

        self._process = await asyncio.create_subprocess_exec(
            self._node_path,
            f"--max-old-space-size={self._max_old_space_size}",
            str(self._worker_script),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self._worker_script.parent),
            limit=50 * 1024 * 1024,
        )
        logger.info("Node.js Worker 已启动 (PID: %d)", self._process.pid)

        ping_result = await self._send_raw({"command": "ping"})
        if ping_result.get("status") != "success":
            raise RuntimeError(f"Node.js Worker 健康检查失败: {ping_result}")

    async def stop(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            logger.info("Node.js Worker 已停止")
        self._process = None

    async def _send_raw(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._process or self._process.returncode is not None:
            await self.start()

        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        raw_line = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=120.0,
        )

        if not raw_line:
            stderr_output = ""
            if self._process.stderr:
                try:
                    stderr_output = (
                        await asyncio.wait_for(
                            self._process.stderr.read(4096), timeout=2.0
                        )
                    ).decode("utf-8", errors="replace")
                except asyncio.TimeoutError:
                    pass
            raise RuntimeError(f"Node.js Worker 无响应。stderr: {stderr_output}")

        return json.loads(raw_line.decode("utf-8"))

    async def parse_files(self, files: list[dict[str, str]]) -> dict[str, Any]:
        async with self._lock:
            return await self._send_raw({"command": "parse", "files": files})

    async def __aenter__(self) -> NodeBridge:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()
