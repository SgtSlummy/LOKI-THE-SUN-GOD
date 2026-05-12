from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loki_research.version_pipeline import write_version_artifacts


def main() -> None:
    artifacts = write_version_artifacts()
    print(f"wrote {artifacts.json_path}")
    print(f"wrote {artifacts.markdown_path}")


if __name__ == "__main__":
    main()
