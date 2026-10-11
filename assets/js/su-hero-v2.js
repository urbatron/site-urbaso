(() => {
  const STAGE_MAX_WIDTH = 1536;
  const STAGE_MIN_WIDTH = 1280;
  const LEFT_COLUMN_MIN = 640;
  const LEFT_COLUMN_MAX = 780;
  const ARTBOARD_WIDTH = 756;

  const getTabletScale = (artboard, layout, viewportWidth) => {
    if (!artboard || !layout) return 1;

    const layoutStyle = getComputedStyle(layout);
    const layoutContentWidth = layout.clientWidth
      - parseFloat(layoutStyle.paddingLeft)
      - parseFloat(layoutStyle.paddingRight);
    const availableWidth = viewportWidth < 900
      ? layoutContentWidth
      : artboard.parentElement.getBoundingClientRect().right
        - artboard.getBoundingClientRect().left;
    return Math.min(1, Math.max(0, availableWidth / ARTBOARD_WIDTH));
  };

  const initSuHero = () => {
    const hero = document.querySelector('#su-hero-v2');
    if (!hero) return;
    const artboard = hero.querySelector('.su-hero-v2__artboard');
    const layout = hero.querySelector('.su-hero-v2__layout');
    let frame = 0;
    let previousWidth;
    let previousHeight;

    const updateSuHero = () => {
      frame = 0;
      const viewportWidth = innerWidth;
      const viewportHeight = innerHeight;
      if (viewportWidth === previousWidth && viewportHeight === previousHeight) return;
      previousWidth = viewportWidth;
      previousHeight = viewportHeight;

      const short = viewportWidth >= STAGE_MIN_WIDTH && viewportHeight < 800;
      const stageWidth = Math.min(viewportWidth, STAGE_MAX_WIDTH);
      const desktopProgress = Math.min(1, Math.max(0,
        (stageWidth - STAGE_MIN_WIDTH) / (STAGE_MAX_WIDTH - STAGE_MIN_WIDTH)
      ));
      const leftColumnWidth = LEFT_COLUMN_MIN
        + (LEFT_COLUMN_MAX - LEFT_COLUMN_MIN) * desktopProgress;
      const artboardSpace = Math.max(0, stageWidth - leftColumnWidth);
      // Read the tablet geometry before any style/class writes. Desktop and
      // mobile use only viewport dimensions and do not force a layout read.
      const scale = viewportWidth >= STAGE_MIN_WIDTH
        ? Math.min(1, artboardSpace / ARTBOARD_WIDTH)
        : viewportWidth >= 768
          ? getTabletScale(artboard, layout, viewportWidth)
          : Math.min(1, artboardSpace / ARTBOARD_WIDTH);

      hero.classList.toggle('su-hero-v2--short', short);
      hero.style.setProperty('--hero-stage-width', `${stageWidth}px`);
      hero.style.setProperty('--hero-left-column', `${leftColumnWidth}px`);
      hero.style.setProperty('--hero-artboard-scale', String(scale));
      hero.style.setProperty('--hero-fluid', String(desktopProgress));
    };

    addEventListener('resize', () => {
      if (!frame) frame = requestAnimationFrame(updateSuHero);
    }, { passive: true });
    updateSuHero();
  };

  // A deferred script runs after parsing. Keep the DOMContentLoaded fallback
  // for other embedding positions without initializing the hero twice.
  if (document.readyState === 'loading') {
    addEventListener('DOMContentLoaded', initSuHero, { once: true });
  } else {
    initSuHero();
  }
})();
