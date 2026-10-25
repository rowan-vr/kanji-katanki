"""Resolve saved dataset choices and check local sources without collection writes."""

import json
import re
from hashlib import sha256
from pathlib import Path

from ..config import DictionaryChoice
from .manager import DictionaryManager
from .registry import list_datasets
from .updates import default_source


def dictionary_sources(
    choices: tuple[DictionaryChoice, ...], *, capability: str | None = None
) -> dict[str, Path]:
    manifests = {item.id: item for item in list_datasets()}
    if len({item.dataset_id for item in choices}) != len(choices):
        raise ValueError("Duplicate dictionary choices.")
    if {item.dataset_id for item in choices} - manifests.keys():
        raise ValueError("Unknown dictionary selection. Saved settings were preserved.")
    selected = {choice.dataset_id: choice for choice in choices}
    paths = {}
    for dataset_id, manifest in manifests.items():
        if capability is None and manifest.format == "target_lists_json":
            continue  # Target-only data must not block dictionary discovery/generation.
        if capability is not None and capability not in manifest.capabilities:
            continue
        choice = selected.get(dataset_id, DictionaryChoice(dataset_id))
        if choice.mode == "disabled":
            continue
        if choice.mode == "bundled":
            if manifest.bundled is None:
                raise ValueError(f"No bundled data available for {manifest.name}.")
            paths[dataset_id] = default_source(manifest)
        else:
            path = Path(choice.path.strip()).expanduser()
            if not path.exists():
                raise ValueError(f"{manifest.name}: the selected local path does not exist.")
            if manifest.format == "jitendex_yomitan" and (
                not path.is_file() or path.suffix.lower() != ".zip"
            ):
                raise ValueError("Jitendex: choose a Yomitan ZIP file.")
            if manifest.format == "kanjidic2_xml" and not path.is_file():
                raise ValueError(f"{manifest.name}: choose an XML or XML.gz file.")
            if manifest.format == "target_lists_json" and not path.is_file():
                raise ValueError(f"{manifest.name}: choose a target-list JSON file.")
            if manifest.format == "kanjivg_svg" and not (
                path.is_dir() or path.suffix.lower() == ".zip"
            ):
                raise ValueError("KanjiVG: choose an SVG directory or canonical SVG ZIP.")
            paths[dataset_id] = path
    return paths


def check_dictionary(choice: DictionaryChoice) -> str:
    manifest = next(item for item in list_datasets() if item.id == choice.dataset_id)
    if choice.mode == "disabled":
        if "target_lists" in manifest.capabilities:
            return "Disabled. This list will not be used for statistics targets."
        return "Disabled. This dataset will not be used for discovery or generation."
    paths = dictionary_sources(
        (choice,), capability="target_lists" if manifest.format == "target_lists_json" else None
    )
    if manifest.format == "target_lists_json":
        from ..stats.sources import load_target_registry
        from .adapters.target_lists_json import TargetListsJson

        path = paths[choice.dataset_id]
        registry = load_target_registry({choice.dataset_id: path})
        adapter = TargetListsJson(path)
        return "\n".join(
            ["Target dataset loaded successfully."]
            + [
                f"{target.title}: {len(target.characters()):,} unique kanji; "
                f"{len(target.groups)} groups; version {target.version}; "
                f"{target.source.attribution}; {target.source.license}"
                for target in registry.lists
            ]
            + list(adapter.warnings)
            + [f"SHA-256 {sha256(path.read_bytes()).hexdigest()}"]
        )
    with DictionaryManager({choice.dataset_id: paths[choice.dataset_id]}) as manager:
        sample = ""
        provider = manager.providers.get("strokes")
        if provider is not None:
            names = (
                (path.name for path in provider.directory.glob("*.svg"))
                if provider.directory.is_dir()
                else provider.archive.namelist()
            )
            name = next(
                (name for name in sorted(names) if re.fullmatch(r"[0-9a-f]{5,6}\.svg", name)), None
            )
            if name is None:
                raise ValueError(
                    "No canonical stroke SVGs found. Select the extracted kanji/ directory."
                )
            character = chr(int(name[:-4], 16))
            if manager.lookup_strokes(character) is None:
                raise ValueError("The sample stroke file could not be loaded.")
            sample = f"\nSample stroke {character} validated; other strokes load on demand."
        words = manager.providers.get("words")
        if words is not None:
            from .adapters.jitendex_yomitan import convert

            payload, index = convert(words.source)
            sample = (
                f"\n{index['term_count']:,} term rows validated; "
                f"{len(json.loads(payload)['words']):,} eligible word forms.\n"
                + words.attribution
                + f"\nSHA-256 {sha256(words.source.read_bytes()).hexdigest()}"
            )
        return (
            "Dataset loaded successfully." + sample + "\n\n" + "\n".join(manager.source_details())
        )
