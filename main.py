"""Root launcher for hosting environments (Discloud, Render, Docker, etc.)."""
import sys
from pathlib import Path

# Ensure src/ is accessible on sys.path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from clubhub.main import main

if __name__ == "__main__":
    main()
