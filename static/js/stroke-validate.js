/* ============================================================
   stroke-validate.js — one reusable client-side input guard.
   Include on any page with numeric or length-limited inputs.

   Why this exists: browsers IGNORE the `maxlength` attribute on
   <input type="number">, so "type a string of 20 zeros" is only
   stoppable in JS. This hardens every number input on the page
   (strip non-digits, cap length, clamp to min/max) and exposes
   clampInput() for inline oninput= handlers.

   The server (validation.py) re-checks everything regardless --
   this layer is purely for instant feedback.
   ============================================================ */
(function () {
  'use strict';

  // Clamp a numeric field in place. Exposed globally so existing inline
  // handlers like oninput="clampInput(this,0,59)" keep working.
  function clampInput(el, min, max) {
    var digits = (el.value || '').replace(/[^0-9]/g, '');
    var cap = String(Math.floor(max)).length;      // no more digits than `max` has
    if (digits.length > cap) digits = digits.slice(0, cap);
    if (digits === '') { el.value = ''; return; }
    var n = parseInt(digits, 10);
    if (n < min) n = min;
    if (n > max) n = max;
    el.value = String(n);
  }
  window.clampInput = clampInput;

  function hardenNumber(el) {
    if (el.dataset.shardened) return;
    el.dataset.shardened = '1';
    var min = el.min !== '' ? parseFloat(el.min) : 0;
    var max = el.max !== '' ? parseFloat(el.max) : null;
    var attrCap = el.getAttribute('maxlength');
    var cap = attrCap ? parseInt(attrCap, 10)
                      : (max != null ? String(Math.floor(max)).length : 9);

    el.addEventListener('input', function () {
      var digits = (el.value || '').replace(/[^0-9]/g, '');
      if (digits.length > cap) digits = digits.slice(0, cap);
      if (digits === '') { el.value = ''; return; }
      var n = parseInt(digits, 10);
      if (max != null && n > max) n = max;      // clamp high while typing
      el.value = String(n);
    });
    el.addEventListener('blur', function () {
      if (el.value === '') return;
      var n = parseInt(el.value, 10);
      if (!isFinite(n)) { el.value = ''; return; }
      if (n < min) n = min;
      if (max != null && n > max) n = max;
      el.value = String(n);
    });
  }

  function harden(root) {
    (root || document).querySelectorAll('input[type="number"]').forEach(hardenNumber);
  }

  if (document.readyState !== 'loading') harden();
  else document.addEventListener('DOMContentLoaded', function () { harden(); });

  // let dynamically-added inputs be hardened on demand
  window.strokeHarden = harden;
})();
