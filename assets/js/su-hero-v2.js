(() => {
  const STAGE_MAX_WIDTH = 1536;
  const STAGE_MIN_WIDTH = 1280;
  const LEFT_COLUMN_MIN = 640;
  const LEFT_COLUMN_MAX = 780;
  const ARTBOARD_WIDTH = 756;

  const getTabletScale = (hero) => {
    const artboard = hero.querySelector('.su-hero-v2__artboard');
    const layout = hero.querySelector('.su-hero-v2__layout');
    if (!artboard || !layout) return 1;

    const layoutStyle = getComputedStyle(layout);
    const layoutContentWidth = layout.clientWidth
      - parseFloat(layoutStyle.paddingLeft)
      - parseFloat(layoutStyle.paddingRight);
    const availableWidth = innerWidth < 900
      ? layoutContentWidth
      : artboard.parentElement.getBoundingClientRect().right
        - artboard.getBoundingClientRect().left;
    return Math.min(1, Math.max(0, availableWidth / ARTBOARD_WIDTH));
  };

  const updateSuHero = () => {
    const hero = document.querySelector('#su-hero-v2');
    if (!hero) return;

    const short = innerWidth >= STAGE_MIN_WIDTH && innerHeight < 800;
    hero.classList.toggle('su-hero-v2--short', short);

    const stageWidth = Math.min(innerWidth, STAGE_MAX_WIDTH);
    const desktopProgress = Math.min(1, Math.max(0,
      (stageWidth - STAGE_MIN_WIDTH) / (STAGE_MAX_WIDTH - STAGE_MIN_WIDTH)
    ));
    const leftColumnWidth = LEFT_COLUMN_MIN
      + (LEFT_COLUMN_MAX - LEFT_COLUMN_MIN) * desktopProgress;
    const artboardSpace = Math.max(0, stageWidth - leftColumnWidth);
    const scale = innerWidth >= STAGE_MIN_WIDTH
      ? Math.min(1, artboardSpace / ARTBOARD_WIDTH)
      : innerWidth >= 768
        ? getTabletScale(hero)
        : Math.min(1, artboardSpace / ARTBOARD_WIDTH);

    hero.style.setProperty('--hero-stage-width', `${stageWidth}px`);
    hero.style.setProperty('--hero-left-column', `${leftColumnWidth}px`);
    hero.style.setProperty('--hero-artboard-scale', String(scale));
    hero.style.setProperty('--hero-fluid', String(desktopProgress));
  };

  addEventListener('DOMContentLoaded', updateSuHero);
  addEventListener('resize', updateSuHero, { passive: true });
  updateSuHero();
})();
