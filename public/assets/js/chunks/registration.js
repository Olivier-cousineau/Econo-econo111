import {
  createNumberFormatter,
  isClientRegistered,
  markClientRegistered,
  resolveClientCount,
  saveUserPayload,
  upsertRegistration,
} from './storage.js';

function clampNonNegative(value) {
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function updateCountDisplays(countNodes, formatter) {
  const resolved = clampNonNegative(resolveClientCount());
  const formatted = formatter.format(resolved);
  countNodes.forEach((node) => {
    node.textContent = formatted;
  });
}

export function initRegistration(options = {}) {
  const {
    overlaySelector = '#registrationOverlay',
    formSelector = '#registrationForm',
    submitSelector = '#registrationSubmit',
    regulationSelector = '#regulationCheckbox',
    countSelector = '[data-client-count]',
    locale = 'fr-CA',
  } = options;

  const overlay = document.querySelector(overlaySelector);
  const form = document.querySelector(formSelector);
  const submitBtn = document.querySelector(submitSelector);
  const regulationCheckbox = document.querySelector(regulationSelector);
  const countNodes = Array.from(document.querySelectorAll(countSelector));
  const formatter = createNumberFormatter(locale);

  function hideOverlay() {
    if (!overlay) return;
    overlay.classList.add('hidden');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('overlay-active');
  }

  function showOverlay() {
    if (!overlay) return;
    overlay.classList.remove('hidden');
    overlay.removeAttribute('aria-hidden');
    document.body.classList.add('overlay-active');
    updateCountDisplays(countNodes, formatter);
  }

  updateCountDisplays(countNodes, formatter);

  if (overlay) {
    if (isClientRegistered()) {
      hideOverlay();
    } else {
      showOverlay();
    }
  }

  if (submitBtn && regulationCheckbox) {
    submitBtn.disabled = !regulationCheckbox.checked;
    regulationCheckbox.addEventListener('change', () => {
      submitBtn.disabled = !regulationCheckbox.checked;
    });
  }

  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;

      const name = form.fullName?.value?.trim() ?? '';
      const email = form.email?.value?.trim() ?? '';
      const registeredAt = new Date().toISOString();
      const payload = { name, email, consent: true, registeredAt };

      const entry = { name, email, registeredAt };

      saveUserPayload(payload);
      upsertRegistration(entry);
      resolveClientCount();
      markClientRegistered();
      updateCountDisplays(countNodes, formatter);
      hideOverlay();
    });
  }

  window.addEventListener('storage', (event) => {
    if (!event) return;
    if (event.key === 'econodealRegistrations' || event.key === 'econodealClientCount') {
      updateCountDisplays(countNodes, formatter);
    }
  });
}
