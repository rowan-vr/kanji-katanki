"""Bound local XML input, reject entities, and never fetch external DTDs."""

import gzip
from pathlib import Path
from xml.etree import ElementTree as ET


def read_xml(path: Path, *, limit: int = 128 * 1024 * 1024):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Dataset exceeds the {limit // 1024} KiB expanded-size limit.")
    return parse_xml(data, name=path.name, limit=limit), data


def parse_xml(data: bytes, *, name: str, limit: int):
    if len(data) > limit:
        raise ValueError(f"XML exceeds expanded-size limit: {name}")
    text = data.decode("utf-8-sig")
    if "<!ENTITY" in text:
        raise ValueError("XML entity declarations are not supported.")
    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"Malformed XML in {name}: {error}") from error
