"""Tappable components with their meaning and the discovered kanji that use them."""

from .word_popup import SCRIPT as WORD_POPUP_SCRIPT

# Reuse the mobile-safe tap handling of the example word popup unchanged.
TAP_SCRIPT = WORD_POPUP_SCRIPT[: WORD_POPUP_SCRIPT.index("  var meaningNodes")]

SCRIPT = (
    r"""<script>
(function() {
  var card = document.currentScript.closest('.katanki-card');
  var box = card.querySelector('.component-panel .components');
  if (!box || !box.querySelector('span[data-meaning]')) return;
  /* TAP */
  var overlay = document.createElement('div');
  overlay.className = 'word-popup-overlay';
  overlay.hidden = true;
  var popup = document.createElement('div');
  popup.className = 'word-popup component-popup';
  popup.setAttribute('role', 'dialog');
  popup.setAttribute('aria-modal', 'true');
  popup.setAttribute('aria-label', 'Component details');
  var close = document.createElement('button');
  close.type = 'button';
  close.className = 'word-popup-close';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close component details');
  var heading = document.createElement('div');
  heading.className = 'word-popup-heading component-popup-heading';
  heading.lang = 'ja';
  var meaning = document.createElement('div');
  meaning.className = 'component-popup-meaning';
  var label = document.createElement('div');
  label.className = 'component-popup-label';
  var list = document.createElement('ul');
  list.className = 'component-popup-kanji';
  var moreLabel = document.createElement('div');
  moreLabel.className = 'component-popup-label';
  moreLabel.textContent = 'Other dictionary kanji';
  var moreList = document.createElement('ul');
  moreList.className = 'component-popup-kanji component-popup-more';
  popup.appendChild(close);
  popup.appendChild(heading);
  popup.appendChild(meaning);
  popup.appendChild(label);
  popup.appendChild(list);
  popup.appendChild(moreLabel);
  popup.appendChild(moreList);
  overlay.appendChild(popup);
  card.appendChild(overlay);
  var opener;
  function dismiss() {
    overlay.hidden = true;
    if (opener) {
      opener.setAttribute('aria-expanded', 'false');
      opener.focus();
    }
  }
  bindWordTap(close, dismiss);
  bindWordTap(overlay, function(event) {
    if (event.target === overlay) dismiss();
  });
  overlay.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') { event.preventDefault(); dismiss(); }
    if (event.key === 'Tab') { event.preventDefault(); close.focus(); }
    event.stopPropagation();
  });
  function fill(target, text) {
    target.textContent = '';
    var rows = text ? text.split('\n').filter(Boolean) : [];
    rows.forEach(function(row) {
      var tab = row.indexOf('\t');
      var item = document.createElement('li');
      var character = document.createElement('span');
      character.className = 'component-kanji';
      character.lang = 'ja';
      character.textContent = tab < 0 ? row : row.slice(0, tab);
      var gloss = document.createElement('span');
      gloss.className = 'component-kanji-meaning';
      gloss.textContent = tab < 0 ? '' : row.slice(tab + 1);
      item.appendChild(character);
      item.appendChild(gloss);
      target.appendChild(item);
    });
    return rows.length;
  }
  function openComponent(button, data) {
    opener = button;
    heading.textContent = data.key;
    meaning.textContent = data.meaning || 'Meaning unavailable.';
    var rows = fill(list, data.kanji);
    label.textContent = rows
      ? 'Used in ' + rows + ' of your kanji'
      : 'Not used in your other discovered kanji';
    moreLabel.hidden = moreList.hidden = !fill(moreList, data.more);
    overlay.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    popup.style.left = '';
    popup.style.top = '';
    if (window.innerWidth > 600) {
      var rect = button.getBoundingClientRect();
      var width = popup.offsetWidth, height = popup.offsetHeight;
      popup.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px';
      popup.style.top = Math.max(12, Math.min(rect.bottom + 8,
        window.innerHeight - height - 12)) + 'px';
    }
    close.focus();
  }
  // Keep field order; plain text between detail spans stays as non-interactive chips.
  var items = [];
  Array.from(box.childNodes).forEach(function(node) {
    if (node.nodeType === 1 && node.dataset && 'meaning' in node.dataset) {
      items.push({key: node.textContent.trim(), meaning: node.dataset.meaning || '',
        kanji: node.dataset.kanji || '', more: node.dataset.more || ''});
    } else {
      (node.textContent || '').split(',').forEach(function(text) {
        if (text.trim()) items.push({key: text.trim()});
      });
    }
  });
  box.textContent = '';
  box.className += ' word-grid';
  items.forEach(function(data) {
    var chip = document.createElement('div');
    chip.className = 'word-chip related-chip component-chip';
    chip.textContent = data.key;
    if ('meaning' in data) {
      chip.className += ' word-definition';
      chip.setAttribute('role', 'button');
      chip.tabIndex = 0;
      chip.setAttribute('aria-haspopup', 'dialog');
      chip.setAttribute('aria-expanded', 'false');
      chip.setAttribute('aria-label', data.key + (data.meaning ? ': ' + data.meaning : ''));
      bindWordTap(chip, function() { openComponent(chip, data); });
      chip.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          event.stopPropagation();
          openComponent(chip, data);
        }
      });
    }
    box.appendChild(chip);
  });
})();
</script>"""
).replace("  /* TAP */\n", TAP_SCRIPT)

CSS = """
.components.word-grid {line-height: 1.6;}
.word-chip.component-chip {font-size: 26px; padding: 4px 14px;}
.component-popup-heading {font-size: 40px; line-height: 1.3; margin-bottom: 4px;}
.component-popup-meaning {font-weight: 600; margin-bottom: 16px;}
.component-popup-label {font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: #69758a; margin-bottom: 6px;}
.component-popup-kanji {list-style: none; margin: 0; padding: 0;}
.component-popup-kanji li {display: flex; gap: 14px; align-items: baseline; padding: 6px 0;
  border-top: 1px solid rgba(0,0,0,.08);}
.component-kanji {font-size: 26px; line-height: 1.3; min-width: 1.2em;}
.component-kanji-meaning {font-size: 15px;}
.component-popup-kanji + .component-popup-label {margin-top: 16px;}
.component-popup-more li {color: #69758a;}
.nightMode .component-popup-more li, .night_mode .component-popup-more li {color: #aab6ca;}
.nightMode .component-popup-label, .night_mode .component-popup-label {color: #aab6ca;}
.nightMode .component-popup-kanji li, .night_mode .component-popup-kanji li {
  border-top-color: rgba(255,255,255,.12);}
@media (max-width: 480px) {
  .word-chip.component-chip {font-size: 22px; padding: 4px 12px;}
}
"""
