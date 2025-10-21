(function () {
  const dictionary = {
    fr: {
      initializing: "Activation du paiement Stripe…",
      processing: "Redirection sécurisée vers Stripe…",
      configError: "Impossible de charger la configuration Stripe. Vérifiez que le serveur est démarré.",
      sessionError: "Impossible de créer la session de paiement Stripe. Réessayez ou contactez le support.",
      redirectError: "Redirection vers Stripe impossible. Vérifiez votre connexion et réessayez.",
      genericError: "Une erreur inattendue est survenue. Merci de réessayer plus tard."
    },
    en: {
      initializing: "Connecting to Stripe…",
      processing: "Redirecting you securely to Stripe…",
      configError: "Stripe configuration could not be loaded. Make sure the backend server is running.",
      sessionError: "Could not create the Stripe checkout session. Please try again or contact support.",
      redirectError: "Unable to redirect to Stripe. Check your connection and try again.",
      genericError: "An unexpected error occurred. Please try again later."
    },
    es: {
      initializing: "Conectando con Stripe…",
      processing: "Redirección segura a Stripe…",
      configError: "No se pudo cargar la configuración de Stripe. Asegúrate de que el servidor esté en ejecución.",
      sessionError: "No se pudo crear la sesión de pago de Stripe. Intenta de nuevo o contacta al soporte.",
      redirectError: "No se pudo redirigir a Stripe. Verifica tu conexión e inténtalo nuevamente.",
      genericError: "Ocurrió un error inesperado. Intenta nuevamente más tarde."
    },
    de: {
      initializing: "Stripe wird verbunden…",
      processing: "Sichere Weiterleitung zu Stripe…",
      configError: "Die Stripe-Konfiguration konnte nicht geladen werden. Bitte stelle sicher, dass der Server läuft.",
      sessionError: "Stripe-Checkout konnte nicht erstellt werden. Versuche es erneut oder kontaktiere den Support.",
      redirectError: "Weiterleitung zu Stripe nicht möglich. Prüfe deine Verbindung und versuche es erneut.",
      genericError: "Ein unerwarteter Fehler ist aufgetreten. Bitte später erneut versuchen."
    },
    it: {
      initializing: "Connessione a Stripe in corso…",
      processing: "Reindirizzamento sicuro verso Stripe…",
      configError: "Impossibile caricare la configurazione di Stripe. Verifica che il server sia attivo.",
      sessionError: "Impossibile creare la sessione di pagamento Stripe. Riprova o contatta il supporto.",
      redirectError: "Impossibile reindirizzare a Stripe. Controlla la connessione e riprova.",
      genericError: "Si è verificato un errore imprevisto. Riprova più tardi."
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const buttons = document.querySelectorAll('[data-stripe-plan]');
    const messageEl = document.getElementById('checkout-message');

    if (!buttons.length || !messageEl) {
      return;
    }

    const locale = (document.documentElement.getAttribute('lang') || 'en').split('-')[0].toLowerCase();
    const strings = dictionary[locale] || dictionary.en;

    let stripe;
    let initPromise;

    function setMessage(text, state) {
      if (!messageEl) {
        return;
      }

      if (!text) {
        messageEl.textContent = '';
        messageEl.setAttribute('hidden', 'hidden');
        messageEl.dataset.state = '';
        return;
      }

      messageEl.textContent = text;
      messageEl.dataset.state = state || 'info';
      messageEl.removeAttribute('hidden');
    }

    async function fetchJsonWithFallback(endpoints, options, defaultErrorMessage) {
      const urls = Array.isArray(endpoints) ? endpoints : [endpoints];
      let lastError;

      for (const url of urls) {
        try {
          const response = await fetch(url, options);
          if (!response.ok) {
            if (response.status === 404) {
              lastError = new Error(defaultErrorMessage || 'Not found');
              lastError.status = 404;
              continue;
            }

            const errorPayload = await response.json().catch(() => ({}));
            const message =
              errorPayload && errorPayload.error
                ? errorPayload.error
                : defaultErrorMessage || 'Request failed';
            const error = new Error(message);
            error.status = response.status;
            throw error;
          }

          return response;
        } catch (error) {
          lastError = error instanceof Error ? error : new Error(defaultErrorMessage || 'Request failed');
        }
      }

      throw lastError || new Error(defaultErrorMessage || 'Request failed');
    }

    async function ensureStripe() {
      if (stripe) {
        return stripe;
      }

      if (initPromise) {
        return initPromise;
      }

      initPromise = (async () => {
        setMessage(strings.initializing, 'info');
        try {
          const response = await fetchJsonWithFallback(
            ['/config', '/api/config'],
            { headers: { Accept: 'application/json' } },
            strings.configError
          );
          const data = await response.json();
          if (!data || !data.publishableKey) {
            throw new Error(strings.configError);
          }
          stripe = Stripe(data.publishableKey);
          setMessage('', 'info');
          return stripe;
        } catch (error) {
          setMessage(error.message || strings.configError, 'error');
          throw error;
        }
      })();

      return initPromise;
    }

    async function createCheckoutSession(payload) {
      const response = await fetchJsonWithFallback(
        ['/create-checkout-session', '/api/create-checkout-session'],
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
          },
          body: JSON.stringify(payload)
        },
        strings.sessionError
      );

      return response.json();
    }

    buttons.forEach((button) => {
      button.addEventListener('click', async () => {
        const plan = button.getAttribute('data-stripe-plan');
        if (!plan) {
          return;
        }

        button.disabled = true;
        button.classList.add('is-loading');

        try {
          await ensureStripe();
          if (!stripe) {
            throw new Error(strings.configError);
          }

          setMessage(strings.processing, 'info');
          const payload = {
            plan,
            locale,
            name: button.getAttribute('data-plan-name') || plan,
            description: button.getAttribute('data-plan-description') || ''
          };

          const session = await createCheckoutSession(payload);
          if (!session || !session.sessionId) {
            throw new Error(strings.sessionError);
          }

          const result = await stripe.redirectToCheckout({ sessionId: session.sessionId });
          if (result.error) {
            throw new Error(result.error.message || strings.redirectError);
          }
        } catch (error) {
          const message = error && error.message ? error.message : strings.genericError;
          setMessage(message, 'error');
        } finally {
          button.disabled = false;
          button.classList.remove('is-loading');
        }
      });
    });
  });
})();
