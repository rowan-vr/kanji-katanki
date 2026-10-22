"""Offline card definitions and escaped content, independent of Anki/Qt."""

import unicodedata
from dataclasses import dataclass
from html import escape

from .planner import NOTE_TYPES, Identity


@dataclass(frozen=True)
class NoteTypeSpec:
    key: str
    name: str
    fields: tuple[str, ...]
    front: str
    back: str


BACK = """{{FrontSide}}<hr id=answer>
<div class="character">{{Display}}</div>
<div>{{Meanings}}</div><div>{{Readings}}</div>
<div>Graphical components: {{Components}}</div>
<div class="strokes">{{Strokes}}</div>
<button type="button" onclick="katankiPlay(this)">Play strokes</button>
<button type="button" onclick="katankiNumbers(this)">Stroke numbers</button>
<div class="attribution">{{Attribution}}</div>
<script>
function katankiNumbers(button) {
  var svg = button.parentNode.querySelector('.strokes svg');
  if (!svg) return;
  var old = svg.querySelectorAll('.katanki-number');
  if (old.length) { old.forEach(function(n) { n.remove(); }); return; }
  svg.querySelectorAll('path').forEach(function(p, i) {
    var point = p.getPointAtLength(0);
    var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('class', 'katanki-number');
    text.setAttribute('x', point.x); text.setAttribute('y', point.y);
    text.setAttribute('fill', '#b03030'); text.setAttribute('font-size', '7');
    text.textContent = i + 1; svg.appendChild(text);
  });
}
function katankiPlay(button) {
  var svg = button.parentNode.querySelector('.strokes svg');
  if (!svg) return;
  svg.querySelectorAll('path').forEach(function(p, i) {
    if (p.katankiAnimation) p.katankiAnimation.cancel();
    var length = p.getTotalLength();
    p.katankiAnimation = p.animate([
      {strokeDasharray: length, strokeDashoffset: length},
      {strokeDasharray: length, strokeDashoffset: 0}
    ], {duration: 450, delay: i * 500, fill: 'both'});
  });
}
</script>"""
CSS = """.card {font-family: sans-serif; text-align: center; font-size: 22px;}
.character {font-size: 72px;}
.strokes {background: white; color: #202020; display: inline-block; margin: 1em;}
.attribution {font-size: 12px; margin-top: 1em;}
button {margin: .3em; padding: .4em;}"""


def note_type_spec(key: str) -> NoteTypeSpec:
    if key not in NOTE_TYPES:
        raise ValueError("Unknown Katanki note type.")
    kind, mode = key.split("-")
    field = "Character" if kind == "kanji" else "Component"
    front = '<div class="character">{{Display}}</div>'
    if kind == "primitive":
        front = (
            '<div>Identify this graphical component:</div><div class="strokes">{{Strokes}}</div>'
        )
    if mode == "production":
        action = "Write the missing kanji:" if kind == "kanji" else "Write the component:"
        front = f"<div>{action}</div>" + "<div>{{Prompt}}</div>"
    return NoteTypeSpec(
        key,
        "Kanji Katanki — " + kind.title() + " " + mode.title(),
        (
            field,
            "Display",
            "Prompt",
            "Meanings",
            "Readings",
            "Components",
            "Strokes",
            "Attribution",
        ),
        front,
        BACK,
    )


@dataclass(frozen=True)
class CardContent:
    identity: Identity
    display: str
    meanings: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    svg: bytes = b""
    prompt: str = ""
    attribution: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    def fields(self) -> dict[str, str]:
        spec = note_type_spec(self.identity.note_type)
        return {
            spec.fields[0]: self.identity.key,
            "Display": escape(self.display),
            "Prompt": "<br>".join(escape(line) for line in self.prompt.split("\n")),
            "Meanings": escape(", ".join(self.meanings)),
            "Readings": escape(", ".join(self.readings)),
            "Components": escape(", ".join(self.components) or "none listed"),
            "Strokes": self.svg.decode("utf-8") if self.svg else "Stroke data unavailable",
            "Attribution": "<br>".join(escape(line) for line in self.attribution),
        }


def normalize_prompt(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split())).casefold()


def vocabulary_prompt(character: str, meanings: tuple[str, ...], vocabulary: tuple[str, ...]):
    """Copy only matching source words and blank every occurrence of the target."""
    examples = tuple(sorted({word for word in vocabulary if character in word}))
    masked = tuple(word.replace(character, "__") for word in examples)
    prompt = "\n".join((", ".join(meanings), "", *masked)) if examples else ""
    return prompt, examples
