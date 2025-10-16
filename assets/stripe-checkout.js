(function () {
  const placeholderToken = 'replace_with';
  const defaultLinks = {
    essential: 'https://buy.stripe.com/test_replace_with_essential_plan',
    advanced: 'https://buy.stripe.com/test_replace_with_advanced_plan',
    premium: 'https://buy.stripe.com/test_replace_with_premium_plan'
  };

  function resolveLinks() {
    const configured = (typeof window !== 'undefined' && window.STRIPE_PAYMENT_LINKS) || {};
    return {
      ...defaultLinks,
      ...configured
    };
  }

  function isPlaceholder(url) {
    return !url || url.indexOf(placeholderToken) !== -1;
  }

  function openCheckout(url) {
    if (!url) {
      return;
    }
    const features = 'noopener=yes,noreferrer=yes';
    window.open(url, '_blank', features);
  }

  document.addEventListener('DOMContentLoaded', function () {
    const links = resolveLinks();
    const buttons = document.querySelectorAll('[data-stripe-plan]');

    buttons.forEach(function (button) {
      const plan = button.getAttribute('data-stripe-plan');
      const missingMessage = button.getAttribute('data-stripe-missing') || 'Configure Stripe payment links in window.STRIPE_PAYMENT_LINKS.';
      const url = links[plan];

      if (isPlaceholder(url)) {
        button.setAttribute('aria-disabled', 'true');
        button.classList.add('stripe-button--disabled');
      }

      button.addEventListener('click', function () {
        const targetUrl = resolveLinks()[plan];
        if (isPlaceholder(targetUrl)) {
          window.alert(missingMessage);
          return;
        }
        openCheckout(targetUrl);
      });
    });
  });
})();
