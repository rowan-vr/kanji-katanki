"""Self-contained review layouts: no host bridge, external assets or network."""

from .furigana import SCRIPT as FURIGANA_SCRIPT
from .word_popup import CSS as WORD_POPUP_CSS
from .word_popup import SCRIPT as WORD_POPUP_SCRIPT

EXAMPLES = r"""<div class="katanki-examples" data-kind="{{CardKind}}">
<div class="managed-examples" hidden>{{VocabExamples}}</div>
<div class="example-output word-grid"></div>
<details class="more-words" hidden>
<summary>Show more words</summary>
<div class="more-word-output word-grid"></div>
</details>
</div>
<script>
(function() {
  /* FURIGANA */
  var root = document.currentScript.previousElementSibling;
  var output = root.querySelector('.example-output'), seen = new Set();
  var labels = {learned: 'Known', relearning: 'Relearning', learning: 'Learning',
    new: 'New', exists: 'Card exists (refresh to update status)', missing: 'No card'};
  var order = {learned: 0, relearning: 1, learning: 2, new: 3, exists: 3, missing: 4};
  var statuses = new Map(), entries = [], readings = new Map();
  var parts = root.dataset.kind === 'primitive', front = root.dataset.side === 'front';
  var limit = Number(root.dataset.limit || 0);
  if (front && limit < 0) { root.closest('.words-section').hidden = true; return; }
  root.querySelectorAll('.managed-examples > div').forEach(function(node) {
    var word = node.textContent.trim(), status = node.dataset.status || 'missing';
    if (node.dataset[front ? 'frontFurigana' : 'backFurigana'] === 'true') {
      readings.set(word, node.dataset.reading || '');
    }
    if (!Object.prototype.hasOwnProperty.call(labels, status)) status = 'missing';
    if (!statuses.has(word) || order[status] < order[statuses.get(word)]) {
      statuses.set(word, status);
    }
  });
  var words = Array.from(root.querySelector('.managed-examples').children)
    .filter(function(n) { return n.dataset[front ? 'front' : 'back'] !== 'false'; })
    .map(function(n) { return n.textContent; });
  words.forEach(function(word) {
    word = word.trim();
    if (!word || seen.has(word)) return;
    seen.add(word);
    entries.push({word: word, status: statuses.get(word) || 'missing', index: entries.length});
  });
  // Deduplicate, then group by study stage with stable ordering within each stage.
  if (!parts && !front) entries.sort(function(a, b) {
    return order[a.status] - order[b.status] || a.index - b.index;
  });
  if (front && limit > 0) entries = entries.slice(0, limit);
  /* WORD_POPUP */
  var more = root.querySelector('.more-words');
  var extra = root.querySelector('.more-word-output');
  entries.forEach(function(entry, index) {
    var interactive = !front && !parts;
    var line = document.createElement('div');
    line.className = front ? 'clue-chip'
      : 'word-chip ' + (parts ? 'related-chip' : 'word-' + entry.status);
    if (interactive) {
      line.setAttribute('role', 'button');
      line.tabIndex = 0;
      line.className += ' word-definition';
      line.setAttribute('aria-haspopup', 'dialog');
      line.setAttribute('aria-expanded', 'false');
      bindWordTap(line, function(event) {
        openDefinition(line, entry.word);
      });
      line.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          event.stopPropagation();
          openDefinition(line, entry.word);
        }
      });
    }
    line.dataset.status = entry.status;
    line.title = front ? entry.word : parts ? 'Related kanji' : labels[entry.status];
    line.setAttribute('aria-label', entry.word + ': ' + line.title);
    line.textContent = entry.word;
    var reading = readings.get(entry.word);
    if (!parts && reading && reading !== entry.word) {
      katankiFurigana(line, entry.word, reading);
    }
    (front || index < 12 ? output : extra).appendChild(line);
  });
  var section = root.closest('.words-section');
  section.querySelector('.word-count').textContent = entries.length;
  if (!front && entries.length > 12) {
    more.hidden = false;
    var summary = more.querySelector('summary');
    var remainder = entries.length - 12;
    function updateSummary() {
      summary.textContent = more.open ? 'Show fewer words' : 'Show ' + remainder + ' more words';
    }
    more.addEventListener('toggle', updateSummary);
    updateSummary();
  }
  if (!entries.length) section.hidden = true;
})();
</script>"""

EXAMPLES = EXAMPLES.replace("/* FURIGANA */", FURIGANA_SCRIPT).replace(
    "/* WORD_POPUP */", WORD_POPUP_SCRIPT
)

STROKE_SCRIPT = r"""<script>
function katankiNumbers(button) {
  var svg = button.closest('.stroke-panel').querySelector('.strokes svg');
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
  var svg = button.closest('.stroke-panel').querySelector('.strokes svg');
  if (!svg) return;
  svg.querySelectorAll('path').forEach(function(p, i) {
    if (p.katankiAnimation) p.katankiAnimation.cancel();
    if (typeof p.animate !== 'function') return;
    var length = p.getTotalLength();
    p.katankiAnimation = p.animate([
      {strokeDasharray: length, strokeDashoffset: length},
      {strokeDasharray: length, strokeDashoffset: 0}
    ], {duration: 450, delay: i * 500, fill: 'both'});
  });
}
(function() {
  var root = document.currentScript.closest('.katanki-card');
  var panel = root.querySelector('.stroke-panel');
  if (!panel.querySelector('svg path')) panel.querySelector('.stroke-actions').hidden = true;
})();
</script>"""

WORD_LEGEND = """<div class="word-legend" aria-label="Word status legend">
<span><i class="legend-dot word-learned"></i>Known</span>
<span><i class="legend-dot word-relearning"></i>Relearning</span>
<span><i class="legend-dot word-learning"></i>Learning</span>
<span><i class="legend-dot word-new"></i>New</span>
<span><i class="legend-dot word-missing"></i>No card</span>
</div>
<p class="status-caption">Status at last creation or refresh</p>
"""

BACK = (
    """<article class="katanki-card answer-card">
<header class="answer-hero">
<div class="eyebrow">{{CardLabel}}</div>
<div class="character" lang="ja">{{Display}}</div>
<div class="meaning">{{Meanings}}</div>
<div class="readings" lang="ja">{{Readings}}</div>
</header>
<div class="answer-details">
<section class="stroke-panel panel">
<h2>Stroke order</h2>
<div class="strokes">{{Strokes}}</div>
<div class="stroke-actions">
<button type="button" onclick="katankiPlay(this)">Play strokes</button>
<button type="button" onclick="katankiNumbers(this)">Stroke numbers</button>
</div>
</section>
<section class="component-panel panel">
<h2>Components</h2>
<div class="components" lang="ja">{{Components}}</div>
</section>
</div>
<section class="words-section panel">
<div class="section-heading"><h2>{{WordsLabel}}</h2><span class="word-count"></span></div>
"""
    + EXAMPLES
    + """
{{WordLegend}}
</section>
<details class="credits"><summary>Sources &amp; credits</summary>
<div class="attribution">{{Attribution}}</div></details>
"""
    + STROKE_SCRIPT
    + """
</article>"""
)

PRODUCTION_FRONT = r"""<article class="katanki-card question-card production-card">
<div class="eyebrow">{{CardLabel}}</div>
<div class="prompt-source" hidden>{{Prompt}}</div>
<div class="production-readings" hidden>{{VocabExamples}}</div>
<div class="production-meaning"></div>
<div class="production-words word-grid" lang="ja"></div>
<div class="writing-space" aria-hidden="true"><span>?</span></div>
<script>
(function() {
  /* FURIGANA */
  var root = document.currentScript.closest('.katanki-card');
  var html = root.querySelector('.prompt-source').innerHTML;
  var lines = html.replace(/<br\s*\/?\s*>|<\/(?:div|p)>/gi, '\n').split('\n')
    .map(function(s) {
      var node = document.createElement('div'); node.innerHTML = s;
      return node.textContent.trim();
    }).filter(Boolean);
  root.querySelector('.production-meaning').textContent = lines.shift() || '';
  var output = root.querySelector('.production-words');
  lines.forEach(function(line) {
    var chip = document.createElement('span'); chip.className = 'clue-chip';
    chip.textContent = line;
    var candidates = Array.from(root.querySelectorAll('.production-readings > div'))
      .filter(function(n) {
        return n.dataset.masked === line;
      });
    var node = candidates[0];
    if (node && node.dataset.frontFurigana === 'true' && node.dataset.reading) {
      var word = node.textContent;
      var target = Array.from(word).find(function(c) {
        return word.split(c).join('__') === line;
      });
      katankiFurigana(chip, word, node.dataset.reading, target);
    }
    output.appendChild(chip);
  });
})();
</script>
</article>"""

PRODUCTION_FRONT = PRODUCTION_FRONT.replace("/* FURIGANA */", FURIGANA_SCRIPT)

RECOGNITION_FRONT = (
    """<article class="katanki-card question-card recognition-card">
<div class="eyebrow">{{CardLabel}}</div>
<div class="character" lang="ja">{{Display}}</div>
<section class="words-section recognition-examples">
<div class="section-heading" hidden><span class="word-count"></span></div>
"""
    + EXAMPLES.replace(
        'data-kind="{{CardKind}}"',
        'data-kind="kanji" data-side="front" data-limit="{{ExampleLimit}}"',
    )
    + "</section></article>"
)

PARTS_FRONT = """<article class="katanki-card question-card parts-card">
<div class="eyebrow">{{CardLabel}}</div>
<div class="strokes">{{Strokes}}</div>
</article>"""

CSS = """.card {
  --kk-bg: #f3f5f9;
  --kk-surface: #ffffff;
  --kk-ink: #202b40;
  --kk-muted: #69758a;
  --kk-line: #e2e7f0;
  --kk-blue: #2864cf;
  --kk-blue-soft: #eaf1ff;
  --kk-missing: #eef0f4;
  --kk-relearning: #9a427a;
  --kk-relearning-soft: #fff0f8;
  --kk-learning: #967000;
  --kk-learning-soft: #fff8dc;
  box-sizing: border-box;
  margin: 0;
  padding: 24px 16px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 20px;
  line-height: 1.6;
  color: var(--kk-ink);
  background: var(--kk-bg);
  text-align: center;
  overflow-wrap: anywhere;
}
.card.nightMode, .nightMode .card, .card.night_mode, .night_mode .card {
  --kk-bg: #151c28;
  --kk-surface: #202a3b;
  --kk-ink: #edf1f8;
  --kk-muted: #aab6ca;
  --kk-line: #35435b;
  --kk-blue: #9cc0ff;
  --kk-blue-soft: #243e65;
  --kk-missing: #2b3342;
  --kk-relearning: #f0a1cf;
  --kk-relearning-soft: #46283e;
  --kk-learning: #e6c66c;
  --kk-learning-soft: #3c3421;
}
.katanki-card, .katanki-card * {box-sizing: border-box;}
.katanki-card [hidden] {display: none !important;}
.katanki-card {max-width: 760px; margin: 0 auto;}
.eyebrow {font-size: 11px; font-weight: 650; letter-spacing: .16em;
  text-transform: uppercase; color: var(--kk-muted);}
.question-card {padding: 48px 24px; min-height: 320px;}
.character {font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans CJK JP", sans-serif;
  font-size: clamp(100px, 25vw, 160px); font-weight: 400; line-height: 1.3;}
.question-card .character {margin: 36px 0 16px;}
.answer-hero {padding: 24px 16px 32px;}
.answer-hero .character {font-size: clamp(88px, 20vw, 120px); margin: 12px 0 8px;}
.meaning, .production-meaning {font-size: 26px; font-weight: 600; line-height: 1.45;}
.readings {font-size: 17px; color: var(--kk-muted); margin-top: 8px;}
.answer-details {display: grid; grid-template-columns: 1fr 1fr; gap: 16px;}
.panel {background: var(--kk-surface); border: 1px solid var(--kk-line);
  border-radius: 18px; padding: 20px; text-align: left; min-width: 0;}
.panel h2 {font-size: 11px; line-height: 1.4; letter-spacing: .12em;
  text-transform: uppercase; font-weight: 650; color: var(--kk-muted); margin: 0 0 16px;}
.strokes {width: 100%; max-width: 190px; margin: 0 auto; padding: 12px;
  background: white; color: #202020; border-radius: 12px; text-align: center; font-size: 15px;}
.strokes svg {display: block; width: 100%; height: auto;}
.parts-card .strokes {margin-top: 36px; max-width: 250px;}
.stroke-actions {display: flex; flex-wrap: wrap; justify-content: center; gap: 8px;
  margin-top: 16px;}
.katanki-card button {min-height: 44px; padding: 8px 12px; font: inherit;
  font-size: 13px; color: var(--kk-ink); border: 1px solid var(--kk-line);
  border-radius: 10px; background: var(--kk-surface); cursor: pointer;
  touch-action: manipulation;}
.katanki-card button:focus-visible, .credits summary:focus-visible {
  outline: 3px solid var(--kk-blue); outline-offset: 3px;}
.components {font-size: 28px; line-height: 1.8;}
.words-section {margin-top: 16px;}
.recognition-examples {margin-top: 24px;}
.recognition-examples .word-grid {justify-content: center;}
.section-heading {display: flex; align-items: baseline; gap: 8px;}
.word-count {font-size: 11px; color: var(--kk-muted);}
.more-words {margin-top: 12px;}
.more-words summary {display: list-item; min-height: 44px; padding: 10px 0;
  font-size: 13px; color: var(--kk-blue); cursor: pointer;}
.more-words summary:focus-visible {outline: 3px solid var(--kk-blue); outline-offset: 3px;}
.word-grid {display: flex; flex-wrap: wrap; gap: 10px;}
.word-chip, .clue-chip {display: inline-block; border-radius: 10px;
  padding: 7px 14px; line-height: 1.6; font-size: 21px; border: 1px solid transparent;}
.word-learned {color: var(--kk-blue); background: var(--kk-blue-soft);
  border-color: var(--kk-blue);}
.related-chip {color: var(--kk-ink); background: var(--kk-bg);}
.word-relearning {color: var(--kk-relearning); background: var(--kk-relearning-soft);
  border-color: var(--kk-relearning); border-style: double; border-width: 3px; padding: 5px 12px;}
.word-learning {color: var(--kk-learning); background: var(--kk-learning-soft);
  border-color: var(--kk-learning); border-style: dashed;}
.word-new, .word-exists {color: var(--kk-ink); background: var(--kk-surface);
  border-color: var(--kk-muted);}
.word-missing {color: var(--kk-muted); background: var(--kk-missing);}
.word-legend {display: flex; flex-wrap: wrap; gap: 16px; margin-top: 24px;
  color: var(--kk-muted); font-size: 11px;}
.word-legend > span {display: inline-flex; gap: 6px; align-items: center;}
.legend-dot {display: inline-block; width: 10px; height: 10px;
  padding: 0; border-width: 1px; border-style: solid; border-radius: 3px;}
.legend-dot.word-relearning {border-style: double; border-width: 3px;}
.legend-dot.word-learning {border-style: dashed;}
.legend-dot.word-missing {border-color: transparent;}
.status-caption {font-size: 11px; margin: 8px 0 0; color: var(--kk-muted);}
.credits {text-align: left; margin: 20px 4px; color: var(--kk-muted); font-size: 12px;}
.credits summary {cursor: pointer; min-height: 44px; padding: 12px 0;}
.attribution {font-size: 11px; line-height: 1.6;}
.production-meaning {margin: 32px 0 24px;}
.production-words {justify-content: center;}
.clue-chip {background: var(--kk-surface); border-color: var(--kk-line);}
.writing-space {width: 112px; height: 112px; margin: 32px auto 0;
  border: 1px dashed var(--kk-line); border-radius: 16px; display: flex;
  align-items: center; justify-content: center; color: var(--kk-muted); font-size: 28px;}
@media (max-width: 480px) {
  .card {padding: 16px 12px; font-size: 18px;}
  .question-card {padding: 32px 12px;}
  .answer-details {grid-template-columns: 1fr; gap: 12px;}
  .panel {padding: 18px; border-radius: 14px;}
  .component-panel {order: -1;}
  .components {font-size: 24px;}
  .meaning, .production-meaning {font-size: 24px;}
  .word-chip, .clue-chip {font-size: 20px; padding: 6px 12px;}
  .word-chip.word-relearning {padding: 4px 10px;}
}
"""

CSS += """
.word-grid {align-items: flex-start; row-gap: 12px;}
.word-grid ruby {ruby-align: center; ruby-position: under;}
.word-grid rt {font-size: .55em; line-height: 1.2; color: var(--kk-muted);}
.word-grid .has-furigana {padding-bottom: 18px; padding-top: 9px;}
.word-grid .word-relearning.has-furigana {padding-bottom: 16px; padding-top: 7px;}
@media (max-width: 480px) {
  .word-grid .has-furigana {padding-bottom: 17px; padding-top: 8px;}
  .word-grid .word-relearning.has-furigana {padding-bottom: 15px; padding-top: 6px;}
}
"""

CSS += WORD_POPUP_CSS
