import json
import subprocess
import sys
from zipfile import ZipFile

from scripts.build_addon import build


def test_archive_is_installable_and_importable_without_anki(tmp_path):
    archive_path = build(tmp_path / "kanji-katanki.ankiaddon")
    with ZipFile(archive_path) as archive:
        assert "__init__.py" in archive.namelist()
        assert "anki/integration.py" in archive.namelist()
        assert not any("__pycache__" in name for name in archive.namelist())
        assert json.loads(archive.read("manifest.json"))["package"] == "katanki"
        archive.extractall(tmp_path / "katanki")
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(tmp_path)!r}); import katanki",
        ],
        check=True,
    )
