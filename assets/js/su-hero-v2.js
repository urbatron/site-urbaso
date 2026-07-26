(() => {
  const updateSuHero = () => {
    const hero = document.querySelector('#su-hero-v2');
    if (!hero) return;

    const short = innerWidth >= 1280 && innerHeight < 800;
    hero.classList.toggle('su-hero-v2--short', short);

    const artboardSpace = Math.max(0, innerWidth - 780);
    const scale = Math.min(1, artboardSpace / 756);
    hero.style.setProperty('--hero-artboard-scale', String(scale));
  };

  addEventListener('DOMContentLoaded', updateSuHero);
  addEventListener('resize', updateSuHero, { passive: true });
  updateSuHero();
})();
