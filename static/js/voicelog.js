/* Voice log — tap-to-dictate into any field, using the browser's built-in
   Web Speech API (no server, no cost). A button with data-voice-target="<id>"
   dictates into the element with that id. Uses event delegation so it also
   works for fields rendered dynamically (e.g. the coach dashboard SPA).
   Silently no-ops in browsers without speech recognition. */
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let active = null; // { rec, btn, target, base }

  function cleanup() {
    if (!active) return;
    active.btn.classList.remove('voice-recording');
    active.btn.removeAttribute('data-recording');
    active = null;
  }

  function stop() {
    if (active) { try { active.rec.stop(); } catch (e) { /* already stopped */ } }
  }

  // Hide voice buttons entirely where speech recognition isn't available,
  // so we never show a control that can't work.
  if (!SR) {
    document.addEventListener('DOMContentLoaded', () => {
      document.querySelectorAll('[data-voice-target]').forEach(b => { b.style.display = 'none'; });
    });
    // Also catch dynamically-added ones via a light interval-free MutationObserver.
    const mo = new MutationObserver(() => {
      document.querySelectorAll('[data-voice-target]').forEach(b => { b.style.display = 'none'; });
    });
    document.addEventListener('DOMContentLoaded', () => mo.observe(document.body, { childList: true, subtree: true }));
    return;
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-voice-target]');
    if (!btn) return;
    e.preventDefault();

    const target = document.getElementById(btn.getAttribute('data-voice-target'));
    if (!target) return;

    // Tapping the active button again stops it.
    if (active && active.btn === btn) { stop(); return; }
    if (active) stop();

    const rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = true;
    rec.continuous = true;
    const base = target.value && target.value.trim() ? target.value.trim() + ' ' : '';
    active = { rec, btn, target, base };
    btn.classList.add('voice-recording');
    btn.setAttribute('data-recording', '1');

    rec.onresult = function (ev) {
      let txt = '';
      for (let i = 0; i < ev.results.length; i++) txt += ev.results[i][0].transcript;
      target.value = base + txt;
      target.dispatchEvent(new Event('input', { bubbles: true }));
    };
    rec.onerror = cleanup;
    rec.onend = cleanup;

    try { rec.start(); } catch (e) { cleanup(); }
  });
})();
