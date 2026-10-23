"""Disposable Jitendex lookup indexes in the add-on's writable user data."""

import json
import logging
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import updates
from .words import WordSuggestions

# Bump when word eligibility, ordering, or the stored lookup structure changes.
FORMAT = 1
MAX_CACHE = 128 * 1024 * 1024
logger = logging.getLogger(__name__)


def location(source):
    if updates.USER_DATA is None:
        return None
    name = sha256(str(source.resolve()).encode()).hexdigest()
    return updates.USER_DATA / "jitendex-cache" / f"{name}.json"


def fingerprint(source):
    with source.open("rb") as stream:
        digest = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path, digest):
    try:
        with path.open("rb") as stream:
            payload = stream.read(MAX_CACHE + 1)
        if len(payload) > MAX_CACHE:
            return None
        data = json.loads(payload)
        if data["format"] != FORMAT or data["source_sha256"] != digest:
            return None
        index = data["index"]
        if not isinstance(index, dict) or any(
            not isinstance(key, str)
            or len(key) != 1
            or not isinstance(rows, list)
            or any(
                not isinstance(row, list)
                or len(row) != 2
                or any(not isinstance(value, str) for value in row)
                or key not in row[0]
                for row in rows
            )
            for key, rows in index.items()
        ):
            return None
        result = WordSuggestions(())
        result.by_character = index
        return result
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None


def save(path, digest, suggestions):
    temporary = None
    try:
        payload = json.dumps(
            {"format": FORMAT, "source_sha256": digest, "index": suggestions.by_character},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        if len(payload) > MAX_CACHE:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        temporary.replace(path)
    except OSError:
        logger.debug("Could not persist Jitendex cache; using memory index", exc_info=True)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
