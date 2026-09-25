(() => {
  const section = document.querySelector('.su-qualification-v1');
  if (!section) return;

  const certificates = [
    'SEO-продвижение и реклама — «Клевер»',
    'Веб-дизайн — «АРТ-СПБ»',
    'Основы программирования на JavaScript — «Амилен»',
    'PHP — «МедиаСемантика» / Epic Skills',
    'Поисковая оптимизация SEO — «Статус»',
    'CMS MODx — «Клевер»',
    '1С-Битрикс: Контент-менеджер',
    '1С-Битрикс: Администратор. Базовый',
    'Битрикс24: сертификат бизнес-партнёра компании «Продвижение сайтов»',
    'Java Tutorial — SoloLearn'
  ].map((title, index) => ({
    title,
    src: `./assets/images/six/${index + 1}.webp`
  }));

  const dialog = section.querySelector('.su-qualification-v1__dialog');
  const image = dialog.querySelector('.su-qualification-v1__full-image');
  const title = dialog.querySelector('.su-qualification-v1__viewer-heading h3');
  const counter = dialog.querySelector('.su-qualification-v1__counter');
  const original = dialog.querySelector('.su-qualification-v1__original');
  const closeButton = dialog.querySelector('.su-qualification-v1__close');
  const previousButton = dialog.querySelector('.su-qualification-v1__arrow--previous');
  const nextButton = dialog.querySelector('.su-qualification-v1__arrow--next');
  const triggers = section.querySelectorAll('[data-su-qualification-index]');
  let currentIndex = 0;
  let opener = null;
  let previousBodyOverflow = '';
  let previousBodyPaddingRight = '';

  const showCertificate = (index) => {
    currentIndex = (index + certificates.length) % certificates.length;
    const certificate = certificates[currentIndex];
    image.src = certificate.src;
    image.alt = certificate.title;
    title.textContent = certificate.title;
    counter.textContent = `${currentIndex + 1} / ${certificates.length}`;
    original.href = certificate.src;
  };

  const lockPage = () => {
    previousBodyOverflow = document.body.style.overflow;
    previousBodyPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    document.body.style.overflow = 'hidden';
  };

  const unlockPage = () => {
    document.body.style.overflow = previousBodyOverflow;
    document.body.style.paddingRight = previousBodyPaddingRight;
  };

  const openViewer = (index, trigger) => {
    opener = trigger;
    showCertificate(index);
    lockPage();
    dialog.showModal();
    closeButton.focus();
  };

  triggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      if (!dialog.showModal) return;
      event.preventDefault();
      openViewer(Number(trigger.dataset.suQualificationIndex), trigger);
    });
  });

  previousButton.addEventListener('click', () => showCertificate(currentIndex - 1));
  nextButton.addEventListener('click', () => showCertificate(currentIndex + 1));
  closeButton.addEventListener('click', () => dialog.close());

  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (outside) dialog.close();
  });

  dialog.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      showCertificate(currentIndex - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      showCertificate(currentIndex + 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      dialog.close();
    } else if (event.key === 'Tab') {
      const focusable = [...dialog.querySelectorAll('button, a[href]')]
        .filter((element) => !element.disabled && element.offsetParent !== null);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  dialog.addEventListener('close', () => {
    unlockPage();
    if (opener) opener.focus();
  });
})();
