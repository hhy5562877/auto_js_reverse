from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_test_env import collect_checks


def run_env_check(level: str) -> None:
    failed = [result for result in collect_checks(level) if result.status == "FAIL"]
    if failed:
        print(f"环境检查未通过，无法运行 {level} 测试：")
        for result in failed:
            print(f"- {result.message}")
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="按层级运行 auto_js_reverse 测试")
    parser.add_argument(
        "--level",
        choices=("unit", "integration", "e2e"),
        default="unit",
        help="要运行的测试层级",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="跳过环境检查，直接运行 pytest",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="透传给 pytest 的额外参数，例如 tests/test_pipeline_resilience.py",
    )
    args = parser.parse_args()

    if not args.skip_check:
        run_env_check(args.level)

    command = [sys.executable, "-m", "pytest", "-m", args.level, *args.pytest_args]
    print("执行命令:", " ".join(command))
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
