"""Versioned, dictionary-independent target lists; no host or UI dependencies."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..common.characters import is_kanji

MAX_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 200_000
MAX_GROUPS = 2_000


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError(f"{field} must be nonempty text (at most 4096 characters).")


def _identity(value, field):
    _text(value, field)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]*", value):
        raise ValueError(f"{field} must be a stable lowercase identifier.")


@dataclass(frozen=True)
class TargetSource:
    title: str
    url: str | None
    revision: str
    license: str
    attribution: str
    authority: str
    sha256: str | None = None

    def __post_init__(self):
        for field in ("title", "revision", "license", "attribution"):
            _text(getattr(self, field), f"source.{field}")
        if self.authority not in ("official", "unofficial", "user"):
            raise ValueError("source.authority must be official, unofficial, or user.")
        if self.url is not None:
            _text(self.url, "source.url")
            url = urlsplit(self.url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("source.url must be HTTPS without credentials, or null.")
        if self.sha256 is not None and (
            not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
        ):
            raise ValueError("source.sha256 must be a SHA-256 digest or null.")


@dataclass(frozen=True)
class TargetGroup:
    id: str
    title: str
    characters: tuple[str, ...]

    def __post_init__(self):
        _identity(self.id, "group.id")
        _text(self.title, "group.title")
        if not isinstance(self.characters, tuple):
            raise ValueError("Group characters must be an immutable tuple.")
        for index, character in enumerate(self.characters):
            if not is_kanji(character):
                raise ValueError(f"Group {self.id}, member {index + 1}: expected one kanji.")
        if len(set(self.characters)) != len(self.characters):
            raise ValueError(f"Group {self.id} contains duplicate characters.")


@dataclass(frozen=True)
class TargetList:
    id: str
    title: str
    version: str
    kind: str
    source: TargetSource
    groups: tuple[TargetGroup, ...]

    def __post_init__(self):
        _identity(self.id, "list.id")
        for field in ("title", "version", "kind"):
            _text(getattr(self, field), f"list.{field}")
        if not isinstance(self.source, TargetSource):
            raise ValueError("List source must contain provenance metadata.")
        if (
            not isinstance(self.groups, tuple)
            or not 0 < len(self.groups) <= MAX_GROUPS
            or any(not isinstance(group, TargetGroup) for group in self.groups)
        ):
            raise ValueError("List must contain between 1 and 2000 groups.")
        if len({group.id for group in self.groups}) != len(self.groups):
            raise ValueError("Duplicate target group IDs.")
        total = sum(len(group.characters) for group in self.groups)
        if not 0 < total <= MAX_MEMBERS:
            raise ValueError("List must contain between 1 and 200000 members.")

    def characters(self, group_ids: tuple[str, ...] | None = None) -> tuple[str, ...]:
        """Union in source group/member order; None selects all, () selects none."""
        if group_ids is not None and set(group_ids) - {group.id for group in self.groups}:
            raise ValueError(f"Unknown group in target list {self.id}.")
        return tuple(
            dict.fromkeys(
                character
                for group in self.groups
                if group_ids is None or group.id in group_ids
                for character in group.characters
            )
        )

    def to_json(self) -> str:
        return (
            json.dumps({"schema_version": 1, **asdict(self)}, ensure_ascii=False, indent=2) + "\n"
        )


@dataclass(frozen=True)
class TargetLoad:
    target_list: TargetList
    warnings: tuple[str, ...] = ()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}.")
        result[key] = value
    return result


def _fields(raw, required, location, optional=()):
    if (
        not isinstance(raw, dict)
        or not required <= raw.keys()
        or raw.keys() - required - set(optional)
    ):
        raise ValueError(f"Invalid {location} fields.")


def parse_target_list(data: bytes) -> TargetLoad:
    if len(data) > MAX_BYTES:
        raise ValueError("Target list exceeds the 4 MiB size limit.")
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_object)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Target list must be a UTF-8 JSON object of bounded depth.") from error
    _fields(raw, {"schema_version", "id", "title", "version", "kind", "source", "groups"}, "list")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unsupported target-list schema version.")
    _fields(
        raw["source"],
        {"title", "url", "revision", "license", "attribution", "authority"},
        "source",
        {"sha256"},
    )
    source = TargetSource(**raw["source"])
    if not isinstance(raw["groups"], list) or not 0 < len(raw["groups"]) <= MAX_GROUPS:
        raise ValueError("Expected between 1 and 2000 target groups.")
    groups, warnings, total = [], [], 0
    for group in raw["groups"]:
        _fields(group, {"id", "title", "characters"}, "group")
        characters = group["characters"]
        if not isinstance(characters, list):
            raise ValueError("Group characters must be a JSON array.")
        total += len(characters)
        if total > MAX_MEMBERS:
            raise ValueError("Target list exceeds the 200000 member limit.")
        # Validate before deduplication, including non-hashable malformed members.
        for index, character in enumerate(characters):
            if not is_kanji(character):
                raise ValueError(f"Group {group['id']}, member {index + 1}: expected one kanji.")
        unique = tuple(dict.fromkeys(characters))
        if len(unique) != len(characters):
            warnings.append(
                f"Group {group['id']}: removed {len(characters) - len(unique)} duplicates."
            )
        groups.append(TargetGroup(group["id"], group["title"], unique))
    return TargetLoad(
        TargetList(raw["id"], raw["title"], raw["version"], raw["kind"], source, tuple(groups)),
        tuple(warnings),
    )


def read_target_list(path: Path) -> TargetLoad:
    with path.open("rb") as stream:
        return parse_target_list(stream.read(MAX_BYTES + 1))


class TargetRegistry:
    """Many classifications coexist; source kind is never a singleton capability."""

    def __init__(self, lists: tuple[TargetList, ...] = ()):
        self._lists: dict[str, TargetList] = {}
        for target_list in lists:
            self.register(target_list)

    @property
    def lists(self) -> tuple[TargetList, ...]:
        return tuple(self._lists.values())

    def register(self, target_list: TargetList) -> None:
        if target_list.id in self._lists:
            raise ValueError(f"Target list ID already registered: {target_list.id}.")
        self._lists[target_list.id] = target_list

    def targets(
        self, selections: tuple[tuple[str, tuple[str, ...] | None], ...]
    ) -> tuple[str, ...]:
        result = {}
        for list_id, group_ids in selections:
            if list_id not in self._lists:
                raise ValueError(f"Unknown target list: {list_id}.")
            result.update(dict.fromkeys(self._lists[list_id].characters(group_ids)))
        return tuple(result)
