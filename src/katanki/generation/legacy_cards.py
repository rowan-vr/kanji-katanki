"""Exact previous stock layouts, retained only for safe template upgrades."""

BACK = r"""{{FrontSide}}<hr id=answer>
<div class="character">{{Display}}</div>
<div>{{Meanings}}</div><div>{{Readings}}</div>
<div>Graphical components: {{Components}}</div>
<div class="katanki-examples" data-limit="{{ExampleLimit}}">
<div class="user-examples" hidden>{{UserExamples}}</div>
<div class="managed-examples" hidden>{{VocabExamples}}</div>
<div class="example-output"></div>
</div>
<script>
(function() {
  var root = document.currentScript.previousElementSibling;
  var output = root.querySelector('.example-output'), seen = new Set();
  var limit = Number(root.dataset.limit), count = 0;
  if (limit < 0) return;
  ['.user-examples', '.managed-examples'].forEach(function(selector) {
    var source = root.querySelector(selector);
    // Managed examples have one div per word. User examples accept one per line.
    var words = selector === '.managed-examples'
      ? Array.from(source.children).map(function(n) { return n.textContent; })
      : source.innerHTML.replace(/<br\s*\/?\s*>|<\/(?:div|p)>/gi, '\n').split('\n')
        .map(function(s) {
          var node = document.createElement('div'); node.innerHTML = s;
          return node.textContent;
        });
    words.forEach(function(word) {
      word = word.trim();
      if (!word || seen.has(word) || (limit && count >= limit)) return;
      seen.add(word); count++;
      var line = document.createElement('div'); line.textContent = word;
      output.appendChild(line);
    });
  });
})();
</script>
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

STYLES = (
    """.card {font-family: sans-serif; text-align: center; font-size: 22px;}
.character {font-size: 72px;}
.strokes {background: white; color: #202020; display: inline-block; margin: 1em;}
.attribution {font-size: 12px; margin-top: 1em;}
button {margin: .3em; padding: .4em;}""",
    """.card {
  box-sizing: border-box;
  max-width: 42rem;
  margin: 0 auto;
  padding: 1.25rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  text-align: center;
  font-size: 22px;
  line-height: 1.65;
  color: #243047;
  background: #f7f8fb;
  overflow-wrap: anywhere;
}
.card *, .card *::before, .card *::after {box-sizing: border-box;}
.character {font-size: clamp(64px, 18vw, 104px); line-height: 1.3; margin: .4em 0;}
#answer {border: 0; border-top: 1px solid #cdd5e2; margin: 1.25rem 0;}
.katanki-examples {margin: 1rem 0;}
.example-output > div {
  margin: .5rem auto;
  padding: .5rem .8rem;
  border: 1px solid #dbe1eb;
  border-radius: .65rem;
  background: #fff;
}
.strokes {
  background: white;
  color: #202020;
  display: block;
  width: 100%;
  max-width: 17rem;
  margin: 1.25rem auto;
  padding: .75rem;
  border-radius: .8rem;
}
.strokes svg {display: block; width: 100%; height: auto;}
.attribution {font-size: 12px; line-height: 1.5; margin-top: 1.5rem; color: #58657a;}
.card button {
  min-height: 44px;
  margin: .3rem;
  padding: .55rem .85rem;
  font: inherit;
  font-size: 16px;
  color: inherit;
  background: #fff;
  border: 1px solid #b9c5d8;
  border-radius: .55rem;
  cursor: pointer;
  touch-action: manipulation;
}
.card button:focus-visible {outline: 3px solid #477bd5; outline-offset: 3px;}
.card.nightMode, .nightMode .card, .card.night_mode, .night_mode .card {
  color: #e5eaf3;
  background: #1b2230;
}
.nightMode .example-output > div, .night_mode .example-output > div,
.nightMode button, .night_mode button {background: #283347; border-color: #53627a;}
.nightMode .attribution, .night_mode .attribution {color: #b3bfd2;}
@media (max-width: 480px) {
  .card {padding: 1rem .75rem; font-size: 20px;}
  .strokes {max-width: 14rem;}
}
""",
)


def front(key):
    kind, mode = key.split("-")
    if mode == "production":
        action = "Write the missing kanji:" if kind == "kanji" else "Write the component:"
        return f"<div>{action}</div>" + "<div>{{Prompt}}</div>"
    if kind == "primitive":
        return '<div>Identify this graphical component:</div><div class="strokes">{{Strokes}}</div>'
    return '<div class="character">{{Display}}</div>'
