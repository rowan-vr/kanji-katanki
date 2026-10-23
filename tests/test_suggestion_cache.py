"""Persistent indexes survive memory resets without trusting dictionary sidecars."""

import json
import os
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from test_jitendex_dictionary import local_dictionary

from katanki.dictionaries import suggestion_cache, updates
from katanki.dictionaries.adapters import jitendex_yomitan as adapter


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "user-data")
    adapter._suggestion_cache.clear()
    source = local_dictionary(tmp_path)
    convert = Mock(wraps=adapter.convert)
    monkeypatch.setattr(adapter, "convert", convert)
    yield source, convert
    adapter._suggestion_cache.clear()


def test_disk_cache_survives_memory_reset_and_preserves_lookup(cache):
    source, convert = cache
    expected = adapter.JitendexYomitan(source).lookup("景")
    assert suggestion_cache.location(source).is_file()
    adapter._suggestion_cache.clear()
    progress = Mock()
    provider = adapter.JitendexYomitan(source, progress=progress)
    assert provider.lookup("景") == expected == ("景観",)
    assert provider.lookup("偽") == ()
    convert.assert_called_once()
    assert "Loaded saved Jitendex index." in [call.args[0] for call in progress.call_args_list]


def test_dictionary_contents_invalidate_disk_cache_even_with_same_stat(cache):
    source, convert = cache
    assert adapter.JitendexYomitan(source).lookup("景") == ("景観",)
    before = source.stat()
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w") as archive:
        for name, payload in entries:
            archive.writestr(
                name, payload.replace(json.dumps("景観").encode(), json.dumps("景色").encode())
            )
    assert source.stat().st_size == before.st_size
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    adapter._suggestion_cache.clear()
    assert adapter.JitendexYomitan(source).lookup("景") == ("景色",)
    assert convert.call_count == 2


@pytest.mark.parametrize("damage", ["json", "shape", "version", "fingerprint"])
def test_invalid_cache_is_rebuilt(cache, damage):
    source, convert = cache
    adapter.JitendexYomitan(source).lookup("景")
    path = suggestion_cache.location(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    if damage == "shape":
        data["index"] = {"景": [[42, "invalid"]]}
    elif damage == "version":
        data["format"] = -1
    elif damage == "fingerprint":
        data["source_sha256"] = "outdated"
    path.write_text("broken" if damage == "json" else json.dumps(data), encoding="utf-8")
    adapter._suggestion_cache.clear()
    assert adapter.JitendexYomitan(source).lookup("景") == ("景観",)
    assert convert.call_count == 2
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == suggestion_cache.FORMAT


def test_unwritable_cache_does_not_block_lookup_or_leave_temporary_files(cache, monkeypatch):
    source, _ = cache
    path = suggestion_cache.location(source)

    def fail(*args, **kwargs):
        raise PermissionError("read-only cache")

    monkeypatch.setattr(type(path), "replace", fail)
    assert adapter.JitendexYomitan(source).lookup("景") == ("景観",)
    assert list(path.parent.iterdir()) == []
