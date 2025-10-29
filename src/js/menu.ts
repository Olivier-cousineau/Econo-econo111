export function initMenu(options = {}) {
  const {
    toggleSelector = '#menuToggle',
    menuSelector = '#headerMenu',
    transitionMs = 200,
  } = options;

  const menuToggle = document.querySelector(toggleSelector);
  const headerMenu = document.querySelector(menuSelector);

  if (!menuToggle || !headerMenu) {
    return;
  }

  const runNextFrame = typeof window.requestAnimationFrame === 'function'
    ? window.requestAnimationFrame.bind(window)
    : (callback) => window.setTimeout(callback, 0);

  let menuHideTimer = null;

  function isMenuOpen() {
    return menuToggle.getAttribute('aria-expanded') === 'true';
  }

  function openMenu() {
    if (menuHideTimer) {
      window.clearTimeout(menuHideTimer);
      menuHideTimer = null;
    }
    headerMenu.hidden = false;
    runNextFrame(() => {
      headerMenu.classList.add('is-visible');
    });
    menuToggle.setAttribute('aria-expanded', 'true');
  }

  function closeMenu(options = {}) {
    const { focusToggle = false } = options;
    headerMenu.classList.remove('is-visible');
    if (menuHideTimer) {
      window.clearTimeout(menuHideTimer);
    }
    menuHideTimer = window.setTimeout(() => {
      headerMenu.hidden = true;
      menuHideTimer = null;
    }, transitionMs);
    menuToggle.setAttribute('aria-expanded', 'false');
    if (focusToggle) {
      menuToggle.focus();
    }
  }

  menuToggle.addEventListener('click', () => {
    if (isMenuOpen()) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  document.addEventListener('click', (event) => {
    if (!isMenuOpen()) return;
    const target = event.target;
    if (target instanceof Element && !headerMenu.contains(target) && !menuToggle.contains(target)) {
      closeMenu();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isMenuOpen()) {
      closeMenu({ focusToggle: true });
    }
  });

  headerMenu.addEventListener('click', (event) => {
    const target = event.target;
    if (target instanceof Element && target.matches('.nav-button')) {
      closeMenu();
    }
  });
}
