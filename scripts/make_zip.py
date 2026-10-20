"""Utility script to generate a clean, deployment-ready ZIP for Discloud."""
import os
import zipfile
from pathlib import Path

def create_discloud_zip(output_filename: str = "clubhub_discloud.zip") -> str:
    root = Path(__file__).parent.parent
    zip_path = root / output_filename

    if zip_path.exists():
        zip_path.unlink()

    root_files = ["main.py", "discloud.config", "config.yaml", "requirements.txt", ".env"]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in root_files:
            fpath = root / fname
            if fpath.exists():
                z.write(fpath, fname)
                print(f"Added: {fname}")

        src_dir = root / "src"
        if src_dir.exists():
            for dirpath, dirnames, filenames in os.walk(src_dir):
                dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.endswith(".egg-info")]
                for filename in filenames:
                    if not filename.endswith((".pyc", ".pyo")):
                        full_path = Path(dirpath) / filename
                        arcname = full_path.relative_to(root).as_posix()
                        z.write(full_path, arcname)
                        print(f"Added: {arcname}")

    print(f"\nCreated clean deployment package: {zip_path.name} ({zip_path.stat().st_size / 1024:.1f} KB)")
    return str(zip_path)

if __name__ == "__main__":
    create_discloud_zip()
