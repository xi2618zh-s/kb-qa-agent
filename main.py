"""Run without installing: python main.py ask "报销期限是多久？" """

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from kb_agent.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
