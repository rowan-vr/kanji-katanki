"""Extract ordered stroke paths; rebuild SVG without active/external content."""

import re
import unicodedata
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from ...common.models import ComponentEntry, StrokeEntry
from .xml_data import parse_xml, read_xml

SVG = "http://www.w3.org/2000/svg"
KVG = "http://kanjivg.tagaini.net"
PATH_DATA = re.compile(r"[MmZzLlHhVvCcSsQqTtAaEe0-9+.,\s-]+")


class KanjiVgSvg:
    def __init__(self, directory: Path):
        self.archive = None
        if not directory.is_dir():
            if not directory.is_file() or directory.suffix.lower() != ".zip":
                raise ValueError("Select a KanjiVG SVG directory or canonical SVG ZIP bundle.")
            try:
                self.archive = ZipFile(directory)
                if sum(info.file_size for info in self.archive.infolist()) > 128 * 1024 * 1024:
                    self.close()
                    raise ValueError("KanjiVG ZIP exceeds the 128 MiB expanded-size limit.")
            except BadZipFile as error:
                raise ValueError("Invalid KanjiVG ZIP archive.") from error
        self.directory = directory
        self.hashes: dict[str, str] = {}

    def lookup_strokes(self, character: str) -> StrokeEntry | None:
        if len(character) != 1:
            raise ValueError("Stroke lookup needs one character.")
        name = f"{ord(character):05x}.svg"
        limit = 1024 * 1024
        if self.directory.is_dir():
            path = self.directory / name
            if not path.exists():
                return None
            root, data = read_xml(path, limit=limit)
        else:
            # Exact canonical member lookup; no archive paths are extracted to disk.
            try:
                archive = self.archive
                if archive is None:
                    raise ValueError("KanjiVG archive has been closed.")
                try:
                    info = archive.getinfo(name)
                except KeyError:
                    return None
                if info.file_size > limit:
                    raise ValueError(f"SVG exceeds expanded-size limit: {name}")
                with archive.open(info) as stream:
                    data = stream.read(limit + 1)
                root = parse_xml(data, name=name, limit=limit)
            except BadZipFile as error:
                raise ValueError("Invalid KanjiVG ZIP archive.") from error
        if root.tag != f"{{{SVG}}}svg":
            raise ValueError(f"Invalid SVG root for {character}.")
        groups = list(root.iter(f"{{{SVG}}}g"))
        matching = [group for group in groups if group.get(f"{{{KVG}}}element") == character]
        if not matching:
            raise ValueError(f"SVG character metadata does not match {character}.")
        strokes = list(matching[0].iter(f"{{{SVG}}}path"))
        if not strokes:
            raise ValueError(f"No stroke paths found for {character}.")
        svg = render_paths(strokes, character)
        component_entries, prerequisites = extract_components(matching[0], character)
        components = tuple(
            dict.fromkeys(
                element
                for node in matching[0].iter()
                if (element := node.get(f"{{{KVG}}}element")) and element != character
            )
        )
        self.hashes[character] = sha256(data).hexdigest()
        return StrokeEntry(character, svg, components, component_entries, prerequisites)

    def close(self):
        if self.archive is not None:
            self.archive.close()
            self.archive = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def render_paths(strokes, character):
    """Rebuild paths without external references, active content or metadata."""
    svg = ET.Element("svg", xmlns=SVG, width="240", height="240", viewBox="0 0 109 109")
    group = ET.SubElement(
        svg,
        "g",
        {
            "fill": "none",
            "stroke": "#202020",
            "stroke-width": "3",
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        },
    )
    for stroke in strokes:
        d = stroke.get("d", "")
        if not PATH_DATA.fullmatch(d):
            raise ValueError(f"Invalid stroke path for {character}.")
        ET.SubElement(group, "path", {"d": d})
    return ET.tostring(svg, encoding="utf-8")


def extract_components(root, character):
    """Preserve graphical hierarchy, without inventing radical or mnemonic names.

    Encoded labels use their NFC character. Unlabelled groups use an upstream
    group ID qualified by the source character, or a path-content fingerprint.
    Split groups are combined in stroke order and deduplicated before planning.
    These provider keys are ordinary Component field content, not note IDs.
    """
    groups = {}

    def visit(node):
        children = []
        for child in node:
            if child.tag == f"{{{SVG}}}g" and list(child.iter(f"{{{SVG}}}path")):
                children.append(visit(child))
        if node is root:
            return tuple(dict.fromkeys(children))
        label = unicodedata.normalize("NFC", node.get(f"{{{KVG}}}element", ""))
        paths = tuple(stroke.get("d", "") for stroke in node.iter(f"{{{SVG}}}path"))
        if label and len(label) == 1 and label != character:
            key = label
        else:
            group_id = node.get("id")
            if group_id:
                key = f"kanjivg:{ord(character):05x}:{group_id}"
            else:
                fingerprint = sha256("\n".join(paths).encode()).hexdigest()
                key = f"kanjivg:paths:{fingerprint}"
        record = groups.setdefault(key, [label, [], []])
        # The same named component may be split across separate graphical groups.
        record[1].extend(node.iter(f"{{{SVG}}}path"))
        record[2].extend(child for child in children if child != key)
        return key

    prerequisites = visit(root)
    entries = tuple(
        ComponentEntry(
            key,
            label or "Unencoded graphical component",
            render_paths(paths, character),
            tuple(dict.fromkeys(children)),
        )
        for key, (label, paths, children) in sorted(groups.items())
    )
    return entries, prerequisites
