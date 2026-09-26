(() => {
  const section = document.querySelector('.su-references-v1');
  if (!section) return;

  const dialog = section.querySelector('.su-references-v1__dialog');
  const closeButton = section.querySelector('.su-references-v1__close');
  const triggers = section.querySelectorAll('[data-su-references-open]');
  let opener = null;
  let scrollY = 0;
  let savedBodyStyles = null;
  let savedHtmlOverflow = '';

  const lockPage = () => {
    scrollY = window.scrollY;
    savedBodyStyles = {
      overflow: document.body.style.overflow,
      paddingRight: document.body.style.paddingRight,
      position: document.body.style.position,
      top: document.body.style.top,
      left: document.body.style.left,
      right: document.body.style.right,
      width: document.body.style.width
    };
    savedHtmlOverflow = document.documentElement.style.overflow;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    Object.assign(document.body.style, {
      overflow: 'hidden',
      position: 'fixed',
      top: `-${scrollY}px`,
      left: '0',
      right: '0',
      width: '100%'
    });
    document.documentElement.style.overflow = 'hidden';
  };

  const unlockPage = () => {
    if (!savedBodyStyles) return;
    Object.assign(document.body.style, savedBodyStyles);
    document.documentElement.style.overflow = savedHtmlOverflow;
    window.scrollTo(0, scrollY);
    savedBodyStyles = null;
  };

  const openLetter = (trigger) => {
    opener = trigger;
    lockPage();
    dialog.showModal();
    closeButton.focus();
  };

  triggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      if (typeof dialog.showModal !== 'function') return;
      event.preventDefault();
      openLetter(trigger);
    });
  });

  closeButton.addEventListener('click', () => dialog.close());

  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (outside) dialog.close();
  });

  dialog.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      dialog.close();
    }
  });

  dialog.addEventListener('close', () => {
    unlockPage();
    if (opener) opener.focus();
  });
})();
