/* rail.js, progressive enhancement for horizontal .h-rail sections.
   For each <div class="rail-wrap"><div class="h-rail">…cards…</div></div>
   it injects prev/next arrows and a dot indicator on tablet/desktop.
   On phones the rail stacks vertically (CSS) and this stays out of the way. */
(function () {
  var ICON_L = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>';
  var ICON_R = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>';

  function isStacked(rail) {
    // matches the CSS breakpoint where the rail becomes a vertical stack
    return window.matchMedia('(max-width: 640px)').matches && !rail.classList.contains('h-rail--chips');
  }

  function initRail(wrap) {
    var rail = wrap.querySelector('.h-rail');
    if (!rail || wrap.dataset.railReady) return;
    wrap.dataset.railReady = '1';

    var prev = document.createElement('button');
    prev.className = 'rail-arrow rail-arrow--prev';
    prev.type = 'button';
    prev.setAttribute('aria-label', 'Scroll left');
    prev.innerHTML = ICON_L;

    var next = document.createElement('button');
    next.className = 'rail-arrow rail-arrow--next';
    next.type = 'button';
    next.setAttribute('aria-label', 'Scroll right');
    next.innerHTML = ICON_R;

    var dots = document.createElement('div');
    dots.className = 'rail-dots';

    wrap.appendChild(prev);
    wrap.appendChild(next);
    wrap.appendChild(dots);

    function page() {
      var first = rail.children[0];
      var step = first ? first.getBoundingClientRect().width + 16 : rail.clientWidth * 0.8;
      return step;
    }

    prev.addEventListener('click', function () { rail.scrollBy({ left: -page(), behavior: 'smooth' }); });
    next.addEventListener('click', function () { rail.scrollBy({ left: page(), behavior: 'smooth' }); });

    function buildDots() {
      dots.innerHTML = '';
      if (isStacked(rail)) return;
      var n = rail.children.length;
      for (var i = 0; i < n; i++) {
        var d = document.createElement('span');
        d.className = 'rail-dot';
        dots.appendChild(d);
      }
    }

    function update() {
      if (isStacked(rail)) {
        prev.style.display = next.style.display = 'none';
        dots.style.display = 'none';
        return;
      }
      var overflow = rail.scrollWidth - rail.clientWidth > 8;
      prev.style.display = next.style.display = overflow ? 'flex' : 'none';
      dots.style.display = overflow ? 'flex' : 'none';
      prev.disabled = rail.scrollLeft <= 4;
      next.disabled = rail.scrollLeft >= rail.scrollWidth - rail.clientWidth - 4;

      var kids = dots.children;
      if (!kids.length) return;
      // highlight the card nearest the left edge
      var idx = Math.round(rail.scrollLeft / (page()));
      for (var i = 0; i < kids.length; i++) kids[i].classList.toggle('active', i === Math.min(idx, kids.length - 1));
    }

    buildDots();
    update();
    rail.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', function () { buildDots(); update(); });
  }

  function initAll() { document.querySelectorAll('.rail-wrap').forEach(initRail); }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else initAll();
})();
