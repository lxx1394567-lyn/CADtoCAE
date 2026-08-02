from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from step04_generate_assembly_script import main


if __name__ == "__main__":
    print("Compatibility wrapper: assembly script generation is now Step04.")
    raise SystemExit(main())
