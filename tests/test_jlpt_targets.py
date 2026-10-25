"""Modern levels are pinned independent targets, never legacy KANJIDIC guesses."""

import json
from hashlib import sha256

import pytest

from katanki.stats.groups import counts_for, coverage_sections
from katanki.stats.progress import CardEvidence, ProgressSnapshot
from katanki.stats.targets import TargetRegistry, parse_target_list
from scripts import generate_jlpt_targets as generator


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    inputs = root / "data/upstream/openjlpt"
    inputs.mkdir(parents=True)
    resources = {}
    for level, character in zip(range(5, 0, -1), "日月火水木", strict=True):
        data = json.dumps([{"character": character, "level": f"N{level}"}]).encode()
        name = f"n{level}.json"
        (inputs / name).write_bytes(data)
        resources[name] = {"sha256": sha256(data).hexdigest()}
    path = root / "datasets/sources/jlpt-openjlpt.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "repository": "https://example.org/openjlpt",
                "revision": "a" * 40,
                "resources": resources,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "ROOT", root)
    return inputs, root / "targets.json", path


def test_generator_preserves_modern_levels_order_provenance_and_portability(source):
    inputs, output, lock = source
    target = generator.generate(inputs, output, version="2026-10-25")
    assert target.characters() == tuple("日月火水木")
    assert [group.id for group in target.groups] == ["n5", "n4", "n3", "n2", "n1"]
    assert target.source.authority == "unofficial"
    assert target.source.revision == "a" * 40
    assert target.source.sha256 == sha256(lock.read_bytes()).hexdigest()
    assert parse_target_list(output.read_bytes()).target_list == target
    before = output.read_bytes()
    generator.generate(inputs, output, version="2026-10-25")
    assert output.read_bytes() == before


@pytest.mark.parametrize("change", ["checksum", "wrong-level", "duplicate", "invalid-kanji"])
def test_generator_rejects_changed_or_invalid_source_before_output(source, change):
    inputs, output, lock_path = source
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    path = inputs / "n1.json"
    if change == "checksum":
        path.write_text("[]", encoding="utf-8")
    else:
        character = "日" if change == "duplicate" else "かな" if change == "invalid-kanji" else "木"
        data = json.dumps(
            [{"character": character, "level": "N2" if change == "wrong-level" else "N1"}]
        ).encode()
        path.write_bytes(data)
        lock["resources"]["n1.json"]["sha256"] = sha256(data).hexdigest()
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(ValueError):
        generator.generate(inputs, output, version="2026-10-25")
    assert not output.exists()


def test_dashboard_level_coverage_keeps_modes_and_omissions_independent(source):
    inputs, output, _ = source
    target = generator.generate(inputs, output, version="2026-10-25")
    registry = TargetRegistry((target,))
    progress = ProgressSnapshot(
        (
            CardEvidence("日", "recognition", 1, 1, "mature", 21, 3, 0),
            CardEvidence("日", "writing", 2, 2, "relearning", 21, 3, 1),
            CardEvidence("亀", "recognition", 3, 3, "young", 1, 1, 0),
        )
    )
    sections = coverage_sections(registry, progress)
    levels = [section for section in sections if section.parent == (target.id, None)]
    assert [section.title for section in levels] == [f"N{n} (unofficial)" for n in range(5, 0, -1)]
    assert counts_for(progress, levels[0].characters, "recognition")["mature"] == 1
    assert counts_for(progress, levels[0].characters, "writing")["relearning"] == 1
    cumulative = registry.targets(((target.id, ("n5", "n4")),))
    assert cumulative == ("日", "月")
    assert "亀" not in registry.targets(((target.id, None),))
    # Neither dictionary availability nor source vocabulary can shrink a denominator.
    assert sum(counts_for(progress, target.characters(), "writing").values()) == 5
