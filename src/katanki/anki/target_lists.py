"""Profile-isolated personal target lists, independent of the Anki runtime."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..stats.targets import TargetList, TargetLoad, parse_target_list, read_target_list


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".target-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@dataclass(frozen=True)
class PersonalTargetPreview:
    loaded: TargetLoad
    existing: TargetList | None
    added: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def unchanged(self) -> bool:
        return self.existing == self.loaded.target_list


class PersonalTargetStore:
    """Each file uses the canonical target-list JSON format, including provenance.

    Invalid stored files fail visibly rather than silently losing user data. A
    replacement requires an explicit flag and an unchanged preview snapshot.
    """

    def __init__(self, root: Path, profile_key: str):
        if not isinstance(profile_key, str) or not profile_key:
            raise ValueError("A nonempty profile key is required.")
        self.directory = Path(root) / "personal-target-lists" / _digest(profile_key)

    def _path(self, list_id: str) -> Path:
        return self.directory / f"{_digest(list_id)}.json"

    def load(self) -> tuple[TargetList, ...]:
        result = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                target = read_target_list(path).target_list
                if path != self._path(target.id):
                    raise ValueError("Stored target list has an unexpected filename.")
            except (OSError, ValueError) as error:
                raise ValueError(
                    f"Cannot load personal target list {path.name}: {error}"
                ) from error
            result.append(target)
        return tuple(sorted(result, key=lambda target: (target.title.casefold(), target.id)))

    def preview(self, path: Path, reserved_ids=()) -> PersonalTargetPreview:
        loaded = read_target_list(Path(path))
        target = loaded.target_list
        if target.id in reserved_ids:
            raise ValueError(f"Target list ID is reserved by a dataset: {target.id}.")
        existing = next((item for item in self.load() if item.id == target.id), None)
        before = existing.characters() if existing else ()
        after = target.characters()
        before_set, after_set = set(before), set(after)
        return PersonalTargetPreview(
            loaded,
            existing,
            tuple(char for char in after if char not in before_set),
            tuple(char for char in before if char not in after_set),
        )

    def install(self, preview: PersonalTargetPreview, replace: bool = False) -> TargetList:
        target = preview.loaded.target_list
        current = next((item for item in self.load() if item.id == target.id), None)
        if current != preview.existing:
            raise ValueError(
                "Personal target list changed after preview; preview the import again."
            )
        if current == target:
            return target
        if current is not None and not replace:
            raise ValueError(f"Explicit replacement required for target list: {target.id}.")
        data = target.to_json().encode("utf-8")
        parse_target_list(data)  # Canonical formatting must also fit the bounded read contract.
        _atomic_write(self._path(target.id), data)
        return target

    def export(self, list_id: str, path: Path) -> None:
        target = self._get(list_id)
        _atomic_write(Path(path), target.to_json().encode("utf-8"))

    def remove(self, list_id: str) -> None:
        self._get(list_id)
        self._path(list_id).unlink()

    def _get(self, list_id: str) -> TargetList:
        for target in self.load():
            if target.id == list_id:
                return target
        raise ValueError(f"Unknown personal target list: {list_id}.")


def store_for_collection(collection) -> PersonalTargetStore:
    """Resolve add-on user_files storage and a stable Anki profile identity."""
    root = Path(__file__).resolve().parents[1] / "user_files" / "target_lists"
    return PersonalTargetStore(root, str(Path(collection.path).resolve().parent))


def get_personal_target_store(mw) -> PersonalTargetStore:
    return store_for_collection(mw.col)
