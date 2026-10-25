"""Load many target classifications through the shared dataset source lifecycle."""

from pathlib import Path

from ..config import DictionaryChoice
from ..dictionaries.adapters.target_lists_json import TargetListsJson
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.registry import bundled_path, list_datasets, verify_bundle
from .targets import TargetRegistry


def load_target_registry(
    sources: dict[str, Path] | None = None,
    *,
    choices: tuple[DictionaryChoice, ...] = (),
) -> TargetRegistry:
    """Resolve bundled, updated, local, or disabled sources using dataset preferences.

    Explicit paths are useful for previews and tests; they bypass preference
    resolution, just like DictionaryManager. No collection access or network I/O.
    """
    manifests = {manifest.id: manifest for manifest in list_datasets()}
    if sources is None:
        sources = dictionary_sources(choices, capability="target_lists")
    if sources.keys() - manifests.keys():
        raise ValueError("Unknown target dataset selection.")
    registry = TargetRegistry()
    for dataset_id, path in sources.items():
        manifest = manifests[dataset_id]
        if "target_lists" not in manifest.capabilities:
            continue
        if manifest.bundled and path.resolve() == bundled_path(manifest.bundled["path"]):
            verify_bundle(manifest)
        if not path.is_file():
            raise ValueError(f"{manifest.name}: choose a target dataset file.")
        compression = {".gz": "gzip", ".zip": "zip"}.get(path.suffix.lower(), "none")
        if compression not in manifest.compression:
            raise ValueError(f"{manifest.name} does not support {compression} input.")
        if manifest.format == "target_lists_json":
            adapter = TargetListsJson(path)
            targets = adapter.target_lists
        else:
            raise ValueError(f"Unsupported target-list adapter: {manifest.format}.")
        for target in targets:
            registry.register(target)
    return registry
