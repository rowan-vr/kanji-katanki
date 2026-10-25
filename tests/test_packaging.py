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
    assert archive_path.stat().st_size < 50_000_000
    with ZipFile(archive_path) as archive:
        assert "__init__.py" in archive.namelist()
        assert "anki/integration.py" in archive.namelist()
        assert "dictionaries/manifests/kanjidic2.json" in archive.namelist()
        assert "dictionaries/manifests/kanjivg.json" in archive.namelist()
        assert "ui/discovery.py" not in archive.namelist()
        assert "ui/refresh.py" in archive.namelist()
        assert "ui/generation.py" in archive.namelist()
        assert "ui/dashboard.py" in archive.namelist()
        assert "ui/statistics_widgets.py" in archive.namelist()
        assert not any(name.startswith("ui/web/") for name in archive.namelist())
        assert not any("node_modules" in name for name in archive.namelist())
        assert "THIRD_PARTY_NOTICES.md" in archive.namelist()
        assert "dictionaries/bundled/kanjidic2.xml" in archive.namelist()
        assert "dictionaries/bundled/kanjivg.zip" in archive.namelist()
        full_export = archive.read("dictionaries/bundled/jitendex.zip")
        lock = json.loads(archive.read("dictionaries/bundled/SOURCES.json"))
        from hashlib import sha256

        assert (
            sha256(full_export).hexdigest() == lock["resources"]["jitendex-yomitan.zip"]["sha256"]
        )
        assert "dictionaries/bundled/licenses/CC-BY-2.0-FR.html" in archive.namelist()
        assert "dictionaries/bundled/NOTICE.txt" in archive.namelist()
        assert "dictionaries/bundled/SOURCES.json" in archive.namelist()
        assert "dictionaries/bundled/licenses/CC-BY-SA-4.0.txt" in archive.namelist()
        assert "dictionaries/bundled/licenses/EDRDG-LICENCE.html" in archive.namelist()
        assert "dictionaries/bundled/licenses/CC-BY-SA-4.0.txt" in archive.namelist()
        assert "dictionaries/bundled/licenses/KanjiVG-COPYING" in archive.namelist()
        assert not any("word_pack" in name for name in archive.namelist())
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
            "from katanki.dictionaries.words import bundled_words; "
            "assert '時間' in bundled_words().lookup('時'); "
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


@pytest.mark.parametrize("changed", [False, True])
def test_notice_verification_accepts_crlf_but_rejects_changed_content(
    tmp_path, monkeypatch, changed
):
    from scripts import build_addon

    source = tmp_path / "src" / "katanki"
    bundled = source / "dictionaries" / "bundled"
    bundled.mkdir(parents=True)
    (bundled / "SOURCES.json").write_text(
        json.dumps({"resources": {}, "derived_notices": {}}), encoding="utf-8"
    )
    (bundled / "NOTICE.txt").write_bytes(b"Attribution\nLicense terms\n")
    text = b"Attribution\r\nLicense terms\r\n"
    if changed:
        text = text.replace(b"Attribution", b"Changed attribution")
    (tmp_path / "THIRD_PARTY_NOTICES.md").write_bytes(text)
    monkeypatch.setattr(build_addon, "ROOT", tmp_path)
    if changed:
        with pytest.raises(ValueError, match="Dataset notice changed"):
            build_addon.verify_bundled_assets(source)
    else:
        build_addon.verify_bundled_assets(source)
