import json
import subprocess
import sys
from zipfile import ZipFile

import pytest

from katanki.dictionaries.registry import bundled_sources
from scripts.build_addon import build


@pytest.mark.skipif(
    not all(path.is_file() for path in bundled_sources().values()),
    reason="Build the add-on first to verify the packaged datasets.",
)
def test_archive_is_installable_and_importable_without_anki(tmp_path):
    archive_path = build(tmp_path / "kanji-katanki.ankiaddon")
    with ZipFile(archive_path) as archive:
        assert "__init__.py" in archive.namelist()
        assert "anki/integration.py" in archive.namelist()
        assert "dictionaries/manifests/kanjidic2.json" in archive.namelist()
        assert "dictionaries/manifests/kanjivg.json" in archive.namelist()
        assert "ui/discovery.py" not in archive.namelist()
        assert "ui/refresh.py" in archive.namelist()
        assert "ui/generation.py" in archive.namelist()
        assert "THIRD_PARTY_NOTICES.md" in archive.namelist()
        assert "dictionaries/bundled/kanjidic2.xml" in archive.namelist()
        assert "dictionaries/bundled/kanjivg.zip" in archive.namelist()
        assert "dictionaries/bundled/licenses/EDRDG-LICENCE.html" in archive.namelist()
        assert "dictionaries/bundled/licenses/CC-BY-SA-4.0.txt" in archive.namelist()
        assert "dictionaries/bundled/licenses/KanjiVG-COPYING" in archive.namelist()
        assert not any("fixtures" in name for name in archive.namelist())
        assert not any("__pycache__" in name for name in archive.namelist())
        assert json.loads(archive.read("manifest.json"))["package"] == "katanki"
        archive.extractall(tmp_path / "katanki")
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
            "from katanki.dictionaries.manager import DictionaryManager; "
            "provider = DictionaryManager(); "
            "assert provider.lookup_kanji('景') is not None; "
            "assert provider.lookup_strokes('景') is not None; provider.close()",
        ],
        check=True,
    )
