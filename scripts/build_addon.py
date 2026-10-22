"""Build a self-contained add-on, with __init__.py at the archive root."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path) -> Path:
    source = ROOT / "src" / "katanki"
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(ROOT / "LICENSE", "LICENSE")
        for path in sorted(source.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(source))
    return output


if __name__ == "__main__":
    print(build(ROOT / "dist" / "kanji-katanki.ankiaddon"))
