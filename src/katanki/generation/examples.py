"""Managed example baselines and editable example text."""

import json
import re
from html.parser import HTMLParser

STATE_FIELD = "KatankiExamplesState"


class UnsupportedStateVersion(ValueError):
    """A newer baseline must not be replaced by an older add-on."""


def managed_fields(fields, identity):
    names = ["VocabExamples", "ExampleLimit", "Attribution"]
    if identity.note_type == "kanji-production":
        names.append("Prompt")
    return {name: fields[name] for name in names}


def encode_state(fields):
    # Anki fields are HTML. Literal tags/entities inside JSON are parsed and
    # rewritten when a note is opened in the editor, corrupting the JSON itself.
    # JSON Unicode escapes preserve the original field strings without exposing
    # markup to the editor. Keep version 1 readable for existing valid records.
    return (
        json.dumps({"version": 1, "fields": fields}, ensure_ascii=False, sort_keys=True)
        .replace("&", r"\u0026")
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
    )


def decode_state(value, expected_fields):
    """Validate the complete baseline before trusting it to protect user edits."""
    recorded = json.loads(value)
    if (
        isinstance(recorded, dict)
        and type(recorded.get("version")) is int
        and recorded["version"] > 1
    ):
        raise UnsupportedStateVersion("Example state was created by a newer add-on")
    if (
        not isinstance(recorded, dict)
        or type(recorded.get("version")) is not int
        or recorded["version"] != 1
        or not isinstance(recorded.get("fields"), dict)
        or set(recorded["fields"]) != set(expected_fields)
        or any(not isinstance(field, str) for field in recorded["fields"].values())
    ):
        raise ValueError("Unsupported or damaged example state")
    return recorded["fields"]


def recover_editor_state(value, expected_fields):
    """Reverse the known quoted-attribute rewrite of legacy raw JSON.

    Never infer a baseline from current note values. Recover only the original
    JSON escapes of our generated attributes, then perform full schema validation.
    Callers must still compare the recovered baseline against the current fields.
    """
    allowed = {
        "data-source": {"vocabulary", "default", "components"},
        "data-status": {"learned", "relearning", "learning", "new", "exists", "missing"},
    }
    pattern = re.compile(r'(data-(?:source|status))="\\&quot;([a-z]+)\\&quot;"')

    def restore(match):
        name, attribute = match.groups()
        if attribute not in allowed[name]:
            return match[0]
        return name + r"=\"" + attribute + r"\""

    recovered = pattern.sub(restore, value)
    if recovered == value:
        raise ValueError("Unrecognized baseline damage")
    return decode_state(recovered, expected_fields)


class _Lines(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "div", "p"}:
            self.text += "\n"

    def handle_endtag(self, tag):
        if tag in {"div", "p"}:
            self.text += "\n"

    def handle_data(self, data):
        self.text += data


def lines(html):
    parser = _Lines()
    parser.feed(html)
    return tuple(line.strip() for line in parser.text.splitlines() if line.strip())


def words_for_side(html, side):
    """Read per-word flags; old unmarked words are available on both sides."""

    class Words(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.included = True
            self.current = []
            self.words = []
            self.marked = False

        def handle_starttag(self, tag, attrs):
            if tag == "div":
                if self.depth == 0:
                    self.marked = True
                    self.current = []
                    self.included = dict(attrs).get("data-" + side) != "false"
                self.depth += 1

        def handle_endtag(self, tag):
            if tag == "div" and self.depth:
                self.depth -= 1
                if self.depth == 0 and self.included:
                    word = "".join(self.current).strip()
                    if word:
                        self.words.append(word)

        def handle_data(self, data):
            if self.depth and self.included:
                self.current.append(data)

    parser = Words()
    parser.feed(html)
    parser.close()
    return tuple(parser.words) if parser.marked else lines(html)
