"""Jitendex participates in the normal dictionary selection/update lifecycle."""

import io
import json
from dataclasses import replace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from dataset_pack_helpers import candidate

from katanki.anki.generation import preview_generation
from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
from katanki.config import CardSettings, DictionaryChoice, Settings, from_dict
from katanki.dictionaries import updates
from katanki.dictionaries.adapters.jitendex_yomitan import JitendexYomitan, convert
from katanki.dictionaries.packs import read_catalog, revision, unpack
from katanki.dictionaries.preferences import check_dictionary, dictionary_sources
from katanki.dictionaries.registry import bundled_path, list_datasets
from katanki.dictionaries.words import selected_words


def local_dictionary(tmp_path):
    _, _, data = candidate(dataset_id="jitendex")
    with ZipFile(io.BytesIO(data)) as archive:
        payload = archive.read("bundled/jitendex.zip")
    path = tmp_path / "custom.zip"
    path.write_bytes(payload)
    return path


def test_local_jitendex_override_persists_checks_and_drives_generation(tmp_path):
    path = local_dictionary(tmp_path)
    choice = DictionaryChoice("jitendex", "local", str(path))
    settings = Settings(
        dictionaries=(choice,),
        cards=(
            CardSettings(example_source="discovered_and_default"),
            CardSettings(),
            CardSettings(),
        ),
    )
    assert from_dict(settings.to_dict()) == settings
    assert dictionary_sources(settings.dictionaries)["jitendex"] == path
    details = check_dictionary(choice)
    assert "1 term rows validated" in details and "SHA-256" in details
    assert "Synthetic test dictionary" in details
    collection = Mock()
    collection.models.all.return_value = []
    report = DiscoveryReport(
        ScanResult(1, ("景",), ("景色",)),
        (KanjiEntry("景", (), (), ("scenery",)),),
        (),
        (),
        True,
        (),
    )
    preview = preview_generation(
        collection,
        report,
        generation_settings=settings,
        allow_missing_decks=True,
        recognition=("景",),
        production=(),
        include_primitives=False,
    )
    assert preview.contents[0].examples == ("景色", "景観")
    assert "Synthetic test dictionary" in preview.contents[0].fields()["Attribution"]
    disabled = replace(settings, dictionaries=(DictionaryChoice("jitendex", "disabled"),))
    preview = preview_generation(
        collection,
        report,
        generation_settings=disabled,
        allow_missing_decks=True,
        recognition=("景",),
        production=(),
        include_primitives=False,
    )
    assert preview.contents[0].examples == ("景色",)
    assert selected_words(disabled.dictionaries).lookup("景") == ()


def test_jitendex_pack_updates_selection_and_falls_back_on_corruption(tmp_path, monkeypatch):
    manifest, release, payload = candidate(dataset_id="jitendex")
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "storage")
    monkeypatch.setattr(updates, "download", Mock(return_value=payload))
    assert updates.install(manifest, release) == release["version"]
    assert selected_words().lookup("景") == ("景観",)
    local = local_dictionary(tmp_path)
    assert selected_words((DictionaryChoice("jitendex", "local", str(local)),)).lookup("景") == (
        "景観",
    )
    assert selected_words((DictionaryChoice("jitendex", "disabled"),)).lookup("景") == ()
    current = updates.installed(manifest)
    assert current is not None
    bundled_path(current[1]["bundled"]["path"], current[0]).write_bytes(b"damaged")
    assert updates.installed(manifest) is None
    assert dictionary_sources(())["jitendex"] == bundled_path(manifest.bundled["path"])


def test_jitendex_use_bundled_keeps_download_and_restores_default(tmp_path, monkeypatch):
    manifest, release, payload = candidate(dataset_id="jitendex")
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "storage")
    monkeypatch.setattr(updates, "download", Mock(return_value=payload))
    updates.install(manifest, release)
    root, _ = updates.installed(manifest)
    updates.use_bundled("jitendex")
    assert root.exists()
    assert dictionary_sources(())["jitendex"] == bundled_path(manifest.bundled["path"])


def test_jitendex_revisions_include_same_day_build_number():
    assert revision("2026.10.03.1") > revision("2026.10.03.0")
    assert revision("2026.10.04.0") > revision("2026.10.03.9999")
    _, release, _ = candidate(dataset_id="jitendex", version="2026.10.03.1")
    assert (
        read_catalog({"schema_version": 1, "datasets": {"jitendex": release}})["jitendex"]
        == release
    )


def test_jitendex_pack_rejects_wrong_inner_version(tmp_path):
    from hashlib import sha256

    manifest, release, payload = candidate(dataset_id="jitendex")
    with ZipFile(io.BytesIO(payload)) as original:
        files = {name: original.read(name) for name in original.namelist()}
    metadata = json.loads(files["PACK.json"])
    metadata["bundled"]["version"] = "2026.10.05.0"
    files["PACK.json"] = json.dumps(metadata).encode()
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    altered = stream.getvalue()
    release = release | {
        "version": "2026.10.05.0",
        "revision": revision("2026.10.05.0"),
        "bytes": len(altered),
        "sha256": sha256(altered).hexdigest(),
    }
    metadata["revision"] = release["revision"]
    # Even matching outer release metadata cannot change the inner dictionary revision.
    files["PACK.json"] = json.dumps(metadata).encode()
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    altered = stream.getvalue()
    release.update(bytes=len(altered), sha256=sha256(altered).hexdigest())
    with pytest.raises(ValueError, match="invalid Jitendex"):
        unpack(altered, manifest.id, release, tmp_path / "stage")


def test_local_reader_rejects_duplicate_banks_and_malformed_rows(tmp_path):
    path = tmp_path / "bad.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "index.json", json.dumps({"title": "test", "revision": "test", "format": 3})
        )
        archive.writestr("term_bank_1.json", json.dumps([["bad"]]))
    with pytest.raises(ValueError, match="term row"):
        convert(path)
    with ZipFile(path, "a") as archive, pytest.warns(UserWarning):
        archive.writestr("term_bank_1.json", "[]")
    with pytest.raises(ValueError, match="Duplicate"):
        JitendexYomitan(path)


def test_local_override_requires_zip(tmp_path):
    with pytest.raises(ValueError, match="Yomitan ZIP"):
        dictionary_sources((DictionaryChoice("jitendex", "local", str(tmp_path)),))


def test_manifest_exposes_words_and_self_contained_notices():
    manifest = next(item for item in list_datasets() if item.id == "jitendex")
    assert manifest.capabilities == ("words",)
    assert "bundled/licenses/EDRDG-LICENCE.html" in manifest.bundled["license_files"]
    assert "bundled/licenses/CC-BY-2.0-FR.html" in manifest.bundled["license_files"]


def test_refresh_uses_local_jitendex_selection(tmp_path, monkeypatch):
    from katanki.anki import example_refresh
    from katanki.generation.cards import CardContent
    from katanki.generation.planner import Identity

    path = local_dictionary(tmp_path)
    identity = Identity("kanji-recognition", "景")

    class Existing(dict):
        id = 1

        def note_type(self):
            from katanki.generation.cards import CSS, note_type_spec

            spec = note_type_spec("kanji-recognition")
            return {"css": CSS, "tmpls": [{"qfmt": spec.front, "afmt": spec.back}]}

    note = Existing(
        CardContent(identity, "景", examples=("景色",), discovered_examples=("景色",)).fields()
    )
    collection = Mock()
    collection.get_note.return_value = note
    monkeypatch.setattr(
        example_refresh,
        "owned_identities",
        lambda col, note_type: {identity: (1,)} if note_type == identity.note_type else {},
    )
    settings = Settings(
        dictionaries=(DictionaryChoice("jitendex", "local", str(path)),),
        cards=(
            CardSettings(example_source="discovered_and_default"),
            CardSettings(),
            CardSettings(),
        ),
    )
    report = DiscoveryReport(
        ScanResult(1, ("景",), ("景色",)),
        (KanjiEntry("景", (), (), ("scenery",)),),
        (),
        (),
        True,
        (),
    )
    plan = example_refresh.plan_example_refresh(collection, report, settings)
    assert len(plan.updates) == 1
    assert "景観" in dict(plan.updates[0].after)["VocabExamples"]
    assert "Synthetic test dictionary" in dict(plan.updates[0].after)["Attribution"]
    disabled = replace(settings, dictionaries=(DictionaryChoice("jitendex", "disabled"),))
    assert not example_refresh.plan_example_refresh(collection, report, disabled).updates


def test_maintainer_refresh_pins_latest_export_in_shared_sources(monkeypatch):
    from katanki.dictionaries import downloads
    from scripts.bundle_datasets import pin_jitendex_release

    immutable = "https://github.com/stephenmk/stephenmk.github.io/releases/download/2026.10.04.0/jitendex-yomitan.zip"
    monkeypatch.setattr(
        downloads,
        "download",
        lambda *args, **kwargs: json.dumps(
            {"assets": [{"name": "jitendex-yomitan.zip", "browser_download_url": immutable}]}
        ).encode(),
    )
    lock = {"resources": {"jitendex-yomitan.zip": {"url": "https://example.org/old.zip"}}}
    pin_jitendex_release(lock)
    assert lock["resources"]["jitendex-yomitan.zip"]["url"] == immutable


def test_replaced_local_zip_invalidates_suggestions_and_ignores_untrusted_sidecars(tmp_path):
    from hashlib import sha256

    path = local_dictionary(tmp_path)
    provider = JitendexYomitan(path)
    assert provider.lookup("景") == ("景観",)
    fake_index = json.dumps({"format": 1, "words": [["景偽", "fake", 9999]]}).encode()
    (tmp_path / "words.json").write_bytes(fake_index)
    (tmp_path / "SOURCES.json").write_text(
        json.dumps(
            {
                "pack_sha256": sha256(fake_index).hexdigest(),
                "resources": {
                    "jitendex-yomitan.zip": {"sha256": sha256(path.read_bytes()).hexdigest()}
                },
            }
        )
    )
    with ZipFile(path) as archive:
        index = archive.read("index.json")
    with ZipFile(path, "w") as archive:
        archive.writestr("index.json", index)
        archive.writestr(
            "term_bank_1.json",
            json.dumps(
                [
                    ["景色", "けしき", "★", "", 200, ["synthetic scenery"], 1, ""],
                ]
            ),
        )
    assert provider.lookup("景") == ("景色",)


def test_jitendex_reports_indexing_progress_and_reuses_cache(tmp_path, monkeypatch):
    from katanki.dictionaries.adapters import jitendex_yomitan as adapter

    path = local_dictionary(tmp_path)
    progress = Mock()
    convert = Mock(wraps=adapter.convert)
    monkeypatch.setattr(adapter, "convert", convert)
    provider = adapter.JitendexYomitan(path, progress=progress)
    assert provider.lookup("景") == ("景観",)
    messages = [call.args[0] for call in progress.call_args_list]
    assert any("bank 1 of 1" in message for message in messages)
    assert "Indexing Jitendex example words…" in messages
    progress.reset_mock()
    assert adapter.JitendexYomitan(path, progress=progress).lookup("景") == ("景観",)
    convert.assert_called_once()
    progress.assert_not_called()
