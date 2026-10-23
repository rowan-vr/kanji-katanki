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


def test_packaging_excludes_downloaded_user_data(tmp_path, monkeypatch):
    from scripts import build_addon

    source = tmp_path / "src" / "katanki"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("# package")
    user_data = source / "user_files" / "dictionaries"
    user_data.mkdir(parents=True)
    (user_data / "active.json").write_text('{"private": true}')
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        (tmp_path / name).write_text("fixture notice")
    monkeypatch.setattr(build_addon, "ROOT", tmp_path)
    monkeypatch.setattr(build_addon, "verify_bundled_assets", lambda _: None)
    with ZipFile(build_addon.build(tmp_path / "addon.ankiaddon")) as archive:
        assert "__init__.py" in archive.namelist()
        assert not any("user_files" in name for name in archive.namelist())
