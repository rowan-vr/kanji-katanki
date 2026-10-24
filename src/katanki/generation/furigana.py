"""Shared offline ruby renderer, using kana as reliable reading boundaries."""

SCRIPT = r"""
function katankiFurigana(container, word, reading, target) {
  function kana(text) {
    return text.replace(/[ァ-ヶ]/g, function(c) {
      return String.fromCharCode(c.charCodeAt(0) - 0x60);
    });
  }
  function masked(text) { return target ? text.split(target).join('__') : text; }
  var chunks = word.match(/[ぁ-ゖァ-ヶー]+|[^ぁ-ゖァ-ヶー]+/g) || [];
  var normalized = kana(reading), solutions = [], steps = 0;
  function align(index, offset, result) {
    // Repeated kana can create multiple valid splits. Never guess between them.
    if (++steps > 2000 || solutions.length > 1) return;
    if (index === chunks.length) {
      if (offset === normalized.length) solutions.push(result);
      return;
    }
    var base = chunks[index], literal = /^[ぁ-ゖァ-ヶー]+$/.test(base);
    if (literal) {
      if (normalized.slice(offset, offset + base.length) === kana(base)) {
        align(index + 1, offset + base.length, result.concat([[base, '']]));
      }
      return;
    }
    for (var end = offset + 1; end <= normalized.length; end++) {
      align(index + 1, end, result.concat([[base, reading.slice(offset, end)]]));
      if (steps > 2000 || solutions.length > 1) break;
    }
  }
  align(0, 0, []);
  var segments = solutions.length === 1 && steps <= 2000
    ? solutions[0] : [[word, reading]];
  container.textContent = '';
  var annotated = false;
  segments.forEach(function(segment) {
    var base = masked(segment[0]), sound = segment[1];
    if (!sound || kana(segment[0]) === kana(sound)) {
      container.appendChild(document.createTextNode(base));
      return;
    }
    var ruby = document.createElement('ruby'), rt = document.createElement('rt');
    ruby.appendChild(document.createTextNode(base)); rt.textContent = sound;
    ruby.appendChild(rt); container.appendChild(ruby); annotated = true;
  });
  container.classList.toggle('has-furigana', annotated);
}
"""
