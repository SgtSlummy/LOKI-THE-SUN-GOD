from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loki_research.hermes_integration import write_hermes_integration_artifacts


def main() -> None:
    artifacts = write_hermes_integration_artifacts()
    print(f"wrote {artifacts.json_path}")
    print(f"wrote {artifacts.markdown_path}")
    print(f"wrote {artifacts.assembly_json_path}")
    print(f"wrote {artifacts.assembly_markdown_path}")
    print(f"wrote {artifacts.final_blueprint_json_path}")
    print(f"wrote {artifacts.final_blueprint_markdown_path}")
    print(f"wrote {artifacts.complete_packages_json_path}")
    print(f"wrote {artifacts.complete_packages_markdown_path}")


if __name__ == "__main__":
    main()
