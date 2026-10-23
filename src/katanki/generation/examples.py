"""Managed example baselines and editable example text."""

import json
from html.parser import HTMLParser

STATE_FIELD = "KatankiExamplesState"


def managed_fields(fields, identity):
    names = ["VocabExamples", "ExampleLimit", "Attribution"]
    if identity.note_type == "kanji-production":
        names.append("Prompt")
    return {name: fields[name] for name in names}


def encode_state(fields):
    return json.dumps({"version": 1, "fields": fields}, ensure_ascii=False, sort_keys=True)


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
