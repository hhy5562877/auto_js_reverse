from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
CONFIG_PATH = ROOT_DIR / ".mcp_config" / "config.json"
NODE_WORKER_DIR = SRC_DIR / "browser_insight" / "node_worker"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from browser_insight.services.browser_connector import _find_chrome_binary


@dataclass
class CheckResult:
    status: str
    message: str


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def has_embedding_key(config: dict) -> bool:
    embedding_cfg = config.get("embedding", {})
    return bool(embedding_cfg.get("api_key") or os.environ.get("SILICONFLOW_API_KEY"))


def check_python_runtime() -> CheckResult:
    if sys.version_info >= (3, 10):
        return CheckResult("PASS", f"Python 版本可用: {sys.version.split()[0]}")
    return CheckResult("FAIL", f"Python 版本过低: {sys.version.split()[0]}，需要 >= 3.10")


def check_python_dependencies() -> CheckResult:
    modules = ("aiohttp", "fastmcp", "lancedb", "pyarrow", "websockets")
    missing = []
    for module in modules:
        try:
            __import__(module)
        except Exception:
            missing.append(module)

    if missing:
        return CheckResult("FAIL", f"缺少 Python 依赖: {', '.join(missing)}")
    return CheckResult("PASS", "Python 核心依赖已安装")


def check_node_runtime() -> CheckResult:
    node_path = shutil.which("node")
    if not node_path:
        return CheckResult("FAIL", "未找到 node，可先安装 Node.js >= 18")
    return CheckResult("PASS", f"Node.js 可用: {node_path}")


def check_node_modules() -> CheckResult:
    node_modules = NODE_WORKER_DIR / "node_modules"
    if node_modules.exists():
        return CheckResult("PASS", f"Node Worker 依赖目录存在: {node_modules}")
    return CheckResult(
        "FAIL",
        f"Node Worker 依赖缺失，请执行: cd {NODE_WORKER_DIR} && npm install",
    )


def check_chrome_binary() -> CheckResult:
    chrome_path = _find_chrome_binary()
    if chrome_path:
        return CheckResult("PASS", f"检测到 Chrome/Chromium: {chrome_path}")
    return CheckResult("FAIL", "未检测到 Chrome/Chromium/Brave/Edge")


def check_config_file() -> CheckResult:
    if CONFIG_PATH.exists():
        return CheckResult("PASS", f"检测到配置文件: {CONFIG_PATH}")
    return CheckResult("WARN", "未找到 .mcp_config/config.json，将使用默认配置")


def check_embedding_key(config: dict) -> CheckResult:
    if has_embedding_key(config):
        return CheckResult("PASS", "检测到 Embedding Key")
    return CheckResult(
        "FAIL",
        "未检测到 SILICONFLOW_API_KEY 或 embedding.api_key，e2e 测试无法完成完整向量链路",
    )


def render_results(level: str, results: Iterable[CheckResult]) -> int:
    exit_code = 0
    print(f"== auto_js_reverse test environment check: {level} ==")
    for result in results:
        print(f"[{result.status}] {result.message}")
        if result.status == "FAIL":
            exit_code = 1
    return exit_code


def collect_checks(level: str) -> list[CheckResult]:
    config = load_config()
    results = [
        check_python_runtime(),
        check_python_dependencies(),
        check_config_file(),
    ]

    if level in {"integration", "e2e", "all"}:
        results.extend(
            [
                check_node_runtime(),
                check_node_modules(),
                check_chrome_binary(),
            ]
        )

    if level in {"e2e", "all"}:
        results.append(check_embedding_key(config))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 auto_js_reverse 测试运行环境")
    parser.add_argument(
        "--level",
        choices=("unit", "integration", "e2e", "all"),
        default="all",
        help="测试层级",
    )
    args = parser.parse_args()

    return render_results(args.level, collect_checks(args.level))


if __name__ == "__main__":
    raise SystemExit(main())
