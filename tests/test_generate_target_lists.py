import json
from hashlib import sha256
from pathlib import Path

import pytest

from scripts import generate_target_lists


@pytest.mark.parametrize("dataset_id", ("school-grades", "joyo"))
def test_generator_creates_reproducible_independent_seed_manifest_and_lock(
    tmp_path, monkeypatch, dataset_id
):
    root = tmp_path / "repo"
    manifests = root / "src/katanki/dictionaries/manifests"
    manifests.mkdir(parents=True)
    original = Path(__file__).parents[1] / "src/katanki/dictionaries/manifests/kanjidic2.json"
    (manifests / "kanjidic2.json").write_bytes(original.read_bytes())
    (root / "datasets").mkdir()
    lock = root / "datasets/bundled-lock.json"
    lock.write_text('{"schema_version": 1, "datasets": {}}', encoding="utf-8")
    monkeypatch.setattr(generate_target_lists, "ROOT", root)
    source = Path(__file__).parent / "fixtures/kanjidic2.xml"
    before = source.read_bytes()
    output = tmp_path / "export.json"
    target = generate_target_lists.generate(
        source, output, version="2026-10-24", bundle=True, dataset_id=dataset_id
    )
    payload = output.read_bytes()
    assert target.version == "2026-10-24"
    assert target.source.revision == "2026-10-22 (synthetic fixture)"
    assert target.source.sha256 == sha256(before).hexdigest()
    assert set(target.characters()) == set("色景")
    seed = root / f"dist/targets/{dataset_id}.json"
    bundle = root / f"src/katanki/dictionaries/bundled/{dataset_id}.json"
    assert seed.read_bytes() == bundle.read_bytes() == payload
    metadata = json.loads((manifests / f"{dataset_id}.json").read_text(encoding="utf-8"))
    assert metadata["format"] == "target_lists_json"
    assert metadata["capabilities"] == ["target_lists"]
    assert metadata["bundled"]["entries"] == 2
    assert metadata["bundled"]["sha256"] == sha256(payload).hexdigest()
    assert json.loads(lock.read_text(encoding="utf-8"))["local_datasets"][dataset_id] == {
        "path": f"dist/targets/{dataset_id}.json",
        "sha256": sha256(payload).hexdigest(),
    }
    generate_target_lists.generate(
        source, output, version="2026-10-24", bundle=True, dataset_id=dataset_id
    )
    assert output.read_bytes() == payload
    assert source.read_bytes() == before
