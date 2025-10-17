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

    const scriptEl = document.currentScript || document.querySelector('script[src*="stripe-checkout.js"]');
    const metaBackend = document.querySelector('meta[name="stripe-backend"]');
    let backendBase = '';
    if (typeof window !== 'undefined' && window.__STRIPE_BACKEND__) {
      backendBase = window.__STRIPE_BACKEND__;
    } else if (scriptEl && scriptEl.dataset && scriptEl.dataset.backend) {
      backendBase = scriptEl.dataset.backend;
    } else if (metaBackend && metaBackend.content) {
      backendBase = metaBackend.content;
    }
    backendBase = (backendBase || '').trim();

    function buildEndpointPaths(resource) {
      const normalised = resource.startsWith('/') ? resource : `/${resource}`;
      if (backendBase) {
        const cleanedBase = backendBase.endsWith('/') ? backendBase.slice(0, -1) : backendBase;
        return [`${cleanedBase}${normalised}`];
      }
      return [normalised, `/api${normalised}`];
    }

    async function requestJson(resource, options, fallbackMessage) {
      const endpoints = buildEndpointPaths(resource);
      let lastError = new Error(fallbackMessage);

      for (let index = 0; index < endpoints.length; index += 1) {
        const url = endpoints[index];
        const isLastAttempt = index === endpoints.length - 1;

        let response;
        try {
          response = await fetch(url, options);
        } catch (networkError) {
          lastError = new Error(fallbackMessage);
          if (!isLastAttempt) {
            continue;
          }
          throw lastError;
        }

        if (!response.ok) {
          if (!isLastAttempt && (response.status === 404 || response.status === 405)) {
            continue;
          }

          const responseClone = response.clone();
          let message = fallbackMessage;
          try {
            const errorPayload = await responseClone.json();
            if (errorPayload && errorPayload.error) {
              message = errorPayload.error;
            }
          } catch (parseError) {
            try {
              const text = await response.text();
              if (text) {
                message = text;
              }
            } catch (textError) {
              // Ignore secondary parsing errors.
            }
          }

          throw new Error(message || fallbackMessage);
        }

        try {
          const data = await response.json();
          if (!data || typeof data !== 'object') {
            throw new Error(fallbackMessage);
          }
          return data;
        } catch (parseError) {
          lastError = new Error(fallbackMessage);
          if (!isLastAttempt) {
            continue;
          }
          throw lastError;
        }
      }

      throw lastError;
    }

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
          const data = await requestJson(
            'config',
            { headers: { 'Accept': 'application/json' } },
            strings.configError
          );
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
      return requestJson(
        'create-checkout-session',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
          },
          body: JSON.stringify(payload)
        },
        strings.sessionError
      );
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
