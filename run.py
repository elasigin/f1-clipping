"""Launcher: `uv run python -I run.py <step>`.

`python -I` ignores the script folder and the working directory, so the project root
is added here explicitly. (An editable install is not used: macOS can mark .venv as
hidden, and Python 3.13 then skips the .pth file that makes it work.)
"""
import runpy
import sys
from pathlib import Path

STEPS = ("fetch", "process", "detect", "figures", "export")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        raise SystemExit(f"usage: python -I run.py [{'|'.join(STEPS)}]")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    runpy.run_module(f"pipeline.{sys.argv[1]}", run_name="__main__")
