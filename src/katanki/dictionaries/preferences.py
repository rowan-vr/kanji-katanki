"""Resolve saved dataset choices and check local sources without collection writes."""

import re
from pathlib import Path

from ..config import DictionaryChoice
from .manager import DictionaryManager
from .registry import bundled_path, list_datasets


def dictionary_sources(choices: tuple[DictionaryChoice, ...]) -> dict[str, Path]:
    manifests = {item.id: item for item in list_datasets()}
    if len({item.dataset_id for item in choices}) != len(choices):
        raise ValueError("Duplicate dictionary choices.")
    if {item.dataset_id for item in choices} - manifests.keys():
        raise ValueError("Unknown dictionary selection. Saved settings were preserved.")
    selected = {choice.dataset_id: choice for choice in choices}
    paths = {}
    for dataset_id, manifest in manifests.items():
        choice = selected.get(dataset_id, DictionaryChoice(dataset_id))
        if choice.mode == "disabled":
            continue
        if choice.mode == "bundled":
            if manifest.bundled is None:
                raise ValueError(f"No bundled data available for {manifest.name}.")
            paths[dataset_id] = bundled_path(manifest.bundled["path"])
        else:
            path = Path(choice.path.strip()).expanduser()
            if not path.exists():
                raise ValueError(f"{manifest.name}: the selected local path does not exist.")
            if manifest.format == "kanjidic2_xml" and not path.is_file():
                raise ValueError(f"{manifest.name}: choose an XML or XML.gz file.")
            if manifest.format == "kanjivg_svg" and not (
                path.is_dir() or path.suffix.lower() == ".zip"
            ):
                raise ValueError("KanjiVG: choose an SVG directory or canonical SVG ZIP.")
            paths[dataset_id] = path
    return paths


def check_dictionary(choice: DictionaryChoice) -> str:
    if choice.mode == "disabled":
        return "Disabled. This dataset will not be used for discovery or generation."
    paths = dictionary_sources((choice,))
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
        return (
            "Dataset loaded successfully." + sample + "\n\n" + "\n".join(manager.source_details())
        )
