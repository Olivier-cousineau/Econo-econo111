(async () => {
  const { initMenu } = await import('./chunks/menu.js');
  const { initRegistration } = await import('./chunks/registration.js');

  initMenu();

  const html = document.documentElement;
  const lang = (html?.lang || 'fr').split('-')[0];

  const LANGUAGE_CONFIGS = {
    fr: {
      locale: 'fr-CA',
      postalMessages: {
        defaultMessage: 'Entrez les 3 premiers caractères du code postal pour trouver les succursales dans un rayon de 50 km (ex. H2X).',
        incomplete: 'Indiquez au moins les 3 premiers caractères du code postal.',
        unknown: 'Code postal non reconnu dans les succursales couvertes.',
      },
      countryOverrides: {
        canada: { titleSuffix: 'Canada' },
      },
      baseCurrencyLocale: 'fr-CA',
    },
    en: {
      locale: 'en-CA',
      postalMessages: {
        defaultMessage: 'Enter the first three characters of the postal code to find branches within a 50 km radius (e.g. H2X).',
        incomplete: 'Enter at least the first three characters of the postal code.',
        unknown: 'Postal code non reconnu dans les succursales couvertes.',
      },
      countryOverrides: {
        canada: {
          emptyNotice: 'Select a store to view the Canadian clearance deals available right now.',
          currency: { code: 'CAD', locale: 'en-CA', cadToLocalRate: 1 },
        },
        usa: {
          titleSuffix: 'United States',
          postalMessage: 'Filters will activate as soon as the US platform launches.',
          emptyNotice: 'We are finalising our US catalogue. Check back soon to discover the best American deals.',
          storeMenuTitle: 'Stores covered at the US launch',
          storeMenuDescription: 'These banners will join our US clearance radar as soon as we officially launch.',
          currency: { code: 'USD', locale: 'en-US', cadToLocalRate: 0.74 },
        },
        europe: {
          postalMessage: 'Search features will be available once the European rollout begins.',
          emptyNotice: 'European coverage is in preparation. Subscribe to be notified of the official launch.',
        },
      },
      baseCurrencyLocale: 'en-CA',
    },
    es: {
      locale: 'es-CA',
      postalMessages: {
        defaultMessage: 'Introduce los tres primeros caracteres del código postal para encontrar sucursales en un radio de 50 km (p. ej., H2X).',
        incomplete: 'Enter at least the first three characters of the postal code.',
        unknown: 'Postal code non reconnu dans les succursales couvertes.',
      },
      countryOverrides: {
        canada: {
          titleSuffix: 'Canadá',
          emptyNotice: 'Selecciona una tienda para ver las liquidaciones disponibles ahora mismo en Canadá.',
          currency: { code: 'CAD', locale: 'es-CA', cadToLocalRate: 1 },
        },
        usa: {
          titleSuffix: 'Estados Unidos',
          postalMessage: 'Los filtros se activarán en cuanto lancemos la plataforma estadounidense.',
          emptyNotice: 'Estamos finalizando nuestro catálogo para EE. UU. Vuelve pronto para descubrir las mejores ofertas americanas.',
          storeMenuTitle: 'Tiendas previstas para el lanzamiento en EE. UU.',
          storeMenuDescription: 'Estas cadenas se añadirán a nuestro radar de liquidaciones en cuanto activemos el lanzamiento oficial.',
          currency: { code: 'USD', locale: 'es-US', cadToLocalRate: 0.74 },
        },
        europe: {
          postalMessage: 'Las funciones de búsqueda estarán disponibles cuando comience el despliegue europeo.',
          emptyNotice: 'La cobertura europea está en preparación. Suscríbete para recibir el aviso del lanzamiento oficial.',
        },
      },
      baseCurrencyLocale: 'es-CA',
    },
    de: {
      locale: 'de-DE',
      postalMessages: {
        defaultMessage: 'Gib die ersten drei Zeichen der Postleitzahl ein, um Filialen im Umkreis von 50\u00a0km zu finden (z.\u00a0B. H2X).',
        incomplete: 'Enter at least the first three characters of the postal code.',
        unknown: 'Postal code non reconnu dans les succursales couvertes.',
      },
      countryOverrides: {
        canada: {
          titleSuffix: 'Kanada',
          emptyNotice: 'Wähle einen Händler, um die aktuell verfügbaren kanadischen Restposten zu sehen.',
          currency: { code: 'CAD', locale: 'de-DE', cadToLocalRate: 1 },
        },
        usa: {
          titleSuffix: 'USA',
          postalMessage: 'Filter werden aktiv, sobald die US-Plattform startet.',
          emptyNotice: 'Wir finalisieren unseren US-Katalog. Schau bald wieder vorbei, um die besten Angebote aus den USA zu entdecken.',
          storeMenuTitle: 'Händler zum US-Start',
          storeMenuDescription: 'Diese Ketten erscheinen auf unserem US-Restpostenradar, sobald wir offiziell starten.',
          currency: { code: 'USD', locale: 'de-DE', cadToLocalRate: 0.74 },
          amazonDomain: 'www.amazon.com',
        },
        europe: {
          postalMessage: 'Suchfunktionen stehen zur Verfügung, sobald der europäische Rollout beginnt.',
          emptyNotice: 'Die europäische Abdeckung wird vorbereitet. Abonniere, um über den offiziellen Start informiert zu werden.',
          amazonDomain: 'www.amazon.de',
        },
      },
      baseCurrencyLocale: 'de-DE',
    },
    it: {
      locale: 'en-CA',
      postalMessages: {
        defaultMessage: 'Enter the first three characters of the postal code to find branches within a 50 km radius (e.g. H2X).',
        incomplete: 'Enter at least the first three characters of the postal code.',
        unknown: 'Postal code non reconnu dans les succursales couvertes.',
      },
      countryOverrides: {
        canada: {
          emptyNotice: 'Select a store to view the Canadian clearance deals available right now.',
          currency: { code: 'CAD', locale: 'en-CA', cadToLocalRate: 1 },
        },
        usa: {
          titleSuffix: 'United States',
          postalMessage: 'Filters will activate as soon as the US platform launches.',
          emptyNotice: 'We are finalising our US catalogue. Check back soon to discover the best American deals.',
          storeMenuTitle: 'Stores covered at the US launch',
          storeMenuDescription: 'These banners will join our US clearance radar as soon as we officially launch.',
          currency: { code: 'USD', locale: 'en-US', cadToLocalRate: 0.74 },
        },
        europe: {
          postalMessage: 'Search features will be available once the European rollout begins.',
          emptyNotice: 'European coverage is in preparation. Subscribe to be notified of the official launch.',
        },
      },
      baseCurrencyLocale: 'en-CA',
    },
  };

  const config = LANGUAGE_CONFIGS[lang] || LANGUAGE_CONFIGS.fr;

  initRegistration({ locale: config.locale });

  const page = html.dataset.page;
  if (page === 'landing') {
    const { initFilters } = await import('./chunks/filters.js');
    await initFilters({
      postalMessages: config.postalMessages,
      countryConfig: config.countryOverrides,
      baseCurrency: { code: 'CAD', locale: config.baseCurrencyLocale },
    });
  }
})();
