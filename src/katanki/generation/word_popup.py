"""Self-contained word definition dialog for desktop and mobile review."""

SCRIPT = r"""
  function bindWordTap(element, activate) {
    // Exclude the word and popup from native mobile reviewer tap zones.
    element.className += ' tappable';
    var start, moved = false, lastTouch = 0;
    // A click property also identifies the chip as interactive to mobile reviewers.
    element.onclick = function(event) {
      event.preventDefault();
      event.stopPropagation();
      if (Date.now() - lastTouch > 700) activate(event);
    };
    element.addEventListener('touchstart', function(event) {
      event.stopPropagation();
      start = event.touches.length === 1 ? event.touches[0] : null;
      moved = false;
    }, {passive: true});
    element.addEventListener('touchmove', function(event) {
      event.stopPropagation();
      var point = event.touches[0];
      if (!start || !point || Math.abs(point.clientX - start.clientX) > 12
          || Math.abs(point.clientY - start.clientY) > 12) moved = true;
    }, {passive: true});
    element.addEventListener('touchend', function(event) {
      event.stopPropagation();
      event.preventDefault();
      lastTouch = Date.now();
      if (start && !moved && event.touches.length === 0) activate(event);
      start = null;
    }, {passive: false});
    element.addEventListener('touchcancel', function(event) {
      event.stopPropagation();
      start = null;
    }, {passive: true});
    ['pointerdown', 'pointerup', 'mousedown', 'mouseup'].forEach(function(type) {
      element.addEventListener(type, function(event) { event.stopPropagation(); });
    });
  }
  var meaningNodes = new Map();
  root.querySelectorAll('.managed-examples > div').forEach(function(node) {
    meaningNodes.set(node.textContent.trim(), {
      reading: node.dataset.reading || '', meaning: node.dataset.meaning || ''
    });
  });
  var overlay = document.createElement('div');
  overlay.className = 'word-popup-overlay';
  overlay.hidden = true;
  var popup = document.createElement('div');
  popup.className = 'word-popup';
  popup.setAttribute('role', 'dialog');
  popup.setAttribute('aria-modal', 'true');
  popup.setAttribute('aria-label', 'Example word meaning');
  var close = document.createElement('button');
  close.type = 'button';
  close.className = 'word-popup-close';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close definition');
  var heading = document.createElement('div');
  heading.className = 'word-popup-heading';
  heading.lang = 'ja';
  var definitions = document.createElement('div');
  definitions.className = 'word-popup-definitions';
  popup.appendChild(close);
  popup.appendChild(heading);
  popup.appendChild(definitions);
  overlay.appendChild(popup);
  root.appendChild(overlay);
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
  function openDefinition(button, word) {
    opener = button;
    var data = meaningNodes.get(word) || {};
    heading.textContent = word + (data.reading ? '【' + data.reading + '】' : '');
    definitions.textContent = '';
    if (data.meaning) {
      var list = document.createElement('ol');
      data.meaning.split('\n').forEach(function(sense) {
        var item = document.createElement('li');
        item.textContent = sense;
        list.appendChild(item);
      });
      definitions.appendChild(list);
    } else definitions.textContent = 'Definition unavailable.';
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
"""

CSS = """
.word-chip.word-definition {cursor: pointer;}
.word-definition[aria-expanded="true"], .word-definition:focus-visible {
  outline: 2px solid currentColor; outline-offset: 3px;}
.word-popup-overlay[hidden] {display: none !important;}
.word-popup-overlay {position: fixed; inset: 0; z-index: 10000; background: rgba(0,0,0,.18);
  display: flex; align-items: center; justify-content: center; text-align: left;}
.word-popup {position: fixed; box-sizing: border-box; width: min(380px, calc(100vw - 24px));
  max-height: calc(100vh - 24px); overflow: auto; padding: 22px; border-radius: 14px;
  background: #fff; color: #242424; box-shadow: 0 8px 32px rgba(0,0,0,.25);
  font-size: 17px; line-height: 1.5; overflow-wrap: anywhere;}
.word-popup-heading {font-size: 23px; padding-right: 30px; margin-bottom: 12px;}
.word-popup-close {position: absolute; top: 4px; right: 4px; width: 44px; height: 44px;
  border: 0; background: transparent; color: inherit; font-size: 28px; cursor: pointer;}
.word-popup-definitions ol {margin: 0; padding-left: 24px;}
.word-popup-definitions li + li {margin-top: 8px;}
.nightMode .word-popup, .night_mode .word-popup {background: #292d33; color: #eee;}
@media (max-width: 600px) {
  .word-popup {position: relative; left: auto !important; top: auto !important;
    max-height: calc(100vh - 48px);}
}
"""
