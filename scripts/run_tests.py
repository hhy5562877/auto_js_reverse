from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_test_env import collect_checks

TEST_LEVELS = ("unit", "integration", "e2e")


def run_env_check(level: str) -> None:
    failed = [result for result in collect_checks(level) if result.status == "FAIL"]
    if failed:
        print(f"环境检查未通过，无法运行 {level} 测试：")
        for result in failed:
            print(f"- {result.message}")
        raise SystemExit(1)


def run_pytest(level: str, pytest_args: list[str]) -> int:
    command = [sys.executable, "-m", "pytest", "-m", level, *pytest_args]
    print(f"执行 {level} 测试命令:", " ".join(command))
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="按层级运行 auto_js_reverse 测试")
    parser.add_argument(
        "--level",
        choices=(*TEST_LEVELS, "all"),
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
        run_env_check("all" if args.level == "all" else args.level)

    if args.level != "all":
        return run_pytest(args.level, args.pytest_args)

    failed_levels: list[str] = []
    for level in TEST_LEVELS:
        print(f"\n== 运行 {level} 测试 ==")
        if run_pytest(level, args.pytest_args) != 0:
            failed_levels.append(level)

    if failed_levels:
        print(f"\n测试失败层级: {', '.join(failed_levels)}")
        return 1

    print(f"\n全部测试层级通过: {', '.join(TEST_LEVELS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
