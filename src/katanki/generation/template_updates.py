"""Upgrade only exact stock templates; preserve user templates and styles."""

import re
from hashlib import sha256

from . import legacy_cards, legacy_layout_v1
from .cards import CSS, note_type_spec
from .layout_fingerprints import (
    PRE_FURIGANA_PAIRS,
    PRE_FURIGANA_STYLE,
    STYLES,
    TEMPLATE_PAIRS,
    USER_EXAMPLES_PAIRS,
    WHOLE_WORD_FURIGANA_PAIRS,
    WHOLE_WORD_FURIGANA_STYLE,
)


def upgrade_stock_layout(model, key):
    """Mutate a model dictionary; caller persists it within the existing Undo group."""
    if len(model.get("tmpls", ())) != 1:
        return False
    spec = note_type_spec(key)
    template = model["tmpls"][0]
    without_examples = re.sub(
        r'<div class="katanki-examples".*?</script>\n',
        "",
        legacy_cards.BACK,
        count=1,
        flags=re.DOTALL,
    )
    old_pair = template["qfmt"] == legacy_cards.front(key) and template["afmt"] in (
        legacy_cards.BACK,
        without_examples,
    )
    kind, mode = key.split("-")
    previous_front = (
        legacy_layout_v1.PRODUCTION_FRONT
        if mode == "production"
        else legacy_layout_v1.PARTS_FRONT
        if kind == "primitive"
        else legacy_layout_v1.RECOGNITION_FRONT
    )
    label = ("Kanji" if kind == "kanji" else "Parts") + " · " + mode.title()
    previous_back = (
        legacy_layout_v1.BACK.replace("{{CardLabel}}", label)
        .replace("{{WordsLabel}}", "Words" if kind == "kanji" else "Related kanji")
        .replace("{{CardKind}}", kind)
        .replace("{{WordLegend}}", legacy_layout_v1.WORD_LEGEND if kind == "kanji" else "")
    )
    early_back = (
        legacy_layout_v1.EARLY_BACK.replace("{{CardLabel}}", label)
        .replace("{{WordsLabel}}", "Words" if kind == "kanji" else "Related kanji")
        .replace("{{WordLegend}}", legacy_layout_v1.WORD_LEGEND.rstrip("\n"))
    )
    old_pair = old_pair or (
        template["qfmt"] == previous_front.replace("{{CardLabel}}", label)
        and template["afmt"] in (previous_back, early_back)
    )
    old_pair = old_pair or (
        sha256(template["qfmt"].encode()).hexdigest(),
        sha256(template["afmt"].encode()).hexdigest(),
    ) in (
        TEMPLATE_PAIRS.get(key),
        PRE_FURIGANA_PAIRS.get(key),
        WHOLE_WORD_FURIGANA_PAIRS.get(key),
        USER_EXAMPLES_PAIRS.get(key),
    )
    stock_pair = template["qfmt"] == spec.front and template["afmt"] == spec.back
    if not (old_pair or stock_pair):
        return False
    changed = False
    if old_pair:
        template["qfmt"], template["afmt"] = spec.front, spec.back
        changed = True
    if model.get("css") in (
        *legacy_cards.STYLES,
        legacy_layout_v1.CSS,
        legacy_layout_v1.EARLY_CSS,
    ) or sha256(model.get("css", "").encode()).hexdigest() in STYLES | {
        PRE_FURIGANA_STYLE,
        WHOLE_WORD_FURIGANA_STYLE,
    }:
        model["css"] = CSS
        changed = True
    return changed
