from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .confluence_client import ConfluenceClient
from .main import load_dotenv


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    client = ConfluenceClient(settings)
    spaces = client.list_all_space_keys()
    allowed = [s for s in spaces if s not in settings.denied_spaces]

    output = {
        "spaceCount": len(spaces),
        "allowedCount": len(allowed),
        "spaces": spaces,
        "allowedSpaces": allowed,
        "envLine": f"ALLOWED_SPACES={','.join(allowed)}",
    }

    out_dir = Path("logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "spaces_discovered.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(output["envLine"])
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
