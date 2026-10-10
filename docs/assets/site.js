// Gentle scroll parallax. The tiled star field stays continuous on long pages.
(() => {
  const sky = document.querySelector('.space-backdrop');
  if (!sky) return;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let scheduled = false;

  function update() {
    scheduled = false;
    const distance = reducedMotion.matches ? 0 : Math.max(0, window.scrollY);
    sky.style.setProperty('--stars-far', `${-(distance * 0.06 % 600)}px`);
    sky.style.setProperty('--stars-near', `${-(distance * 0.12 % 600)}px`);
  }

  function onScroll() {
    if (scheduled || reducedMotion.matches) return;
    scheduled = true;
    window.requestAnimationFrame(update);
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  reducedMotion.addEventListener('change', update);
  window.addEventListener('pageshow', update);
  update();
})();
