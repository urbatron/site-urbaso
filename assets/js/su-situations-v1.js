(() => {
  const section = document.querySelector('.su-situations-v1');
  if (!section) return;

  const tabs = [...section.querySelectorAll('[role="tab"]')];
  const panels = [...section.querySelectorAll('[role="tabpanel"]')];
  const answer = section.querySelector('.su-situations-v1__answer');
  // Below 1024px the answer sits underneath the tabs rather than beside them.
  const stackedLayout = window.matchMedia('(max-width: 1023px)');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let pendingScroll = 0;
  const activeImages = tabs.map((_, index) => `/assets/images/eight/${index + 1}_blue.webp`);
  activeImages.forEach((source) => { const image = new Image(); image.src = source; });

  const selectTab = (tab, moveFocus = false) => {
    window.cancelAnimationFrame(pendingScroll);
    pendingScroll = 0;
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => { panel.hidden = panel.id !== tab.getAttribute('aria-controls'); });
    if (moveFocus) tab.focus();
  };

  const revealAnswer = () => {
    if (!answer || !stackedLayout.matches) return;
    // Measure after the new panel has changed the paper height. Keep the photo
    // and the start of the answer in view without moving keyboard focus.
    pendingScroll = window.requestAnimationFrame(() => {
      pendingScroll = 0;
      if (!stackedLayout.matches) return;
      window.scrollTo({
        top: Math.max(0, window.scrollY + answer.getBoundingClientRect().top - 16),
        behavior: reducedMotion.matches ? 'auto' : 'smooth',
      });
    });
  };

  section.classList.add('su-situations-v1--ready');
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => {
      selectTab(tab);
      revealAnswer();
    });
    tab.addEventListener('keydown', (event) => {
      let nextIndex;
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
      if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') nextIndex = 0;
      if (event.key === 'End') nextIndex = tabs.length - 1;
      if (nextIndex === undefined) return;
      event.preventDefault();
      selectTab(tabs[nextIndex], true);
    });
  });
  selectTab(tabs[0]);
})();
