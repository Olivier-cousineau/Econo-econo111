const PUBLISHABLE_KEY_CANDIDATES = [
  'STRIPE_PUBLISHABLE_KEY',
  'NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY',
  'STRIPE_PUBLIC_KEY',
];

const SECRET_KEY_CANDIDATES = [
  'STRIPE_SECRET_KEY',
  'STRIPE_SECRET',
  'STRIPE_API_KEY',
];

const BASE_URL_CANDIDATES = [
  'STRIPE_BASE_URL',
  'NEXT_PUBLIC_APP_URL',
  'NEXT_PUBLIC_SITE_URL',
  'SITE_URL',
];

export function resolvePublishableKey(env = process.env) {
  for (const variable of PUBLISHABLE_KEY_CANDIDATES) {
    const value = env?.[variable];
    if (value) {
      return value;
    }
  }
  return null;
}

export function resolveStripeSecretKey(env = process.env) {
  for (const variable of SECRET_KEY_CANDIDATES) {
    const value = env?.[variable];
    if (value) {
      return value;
    }
  }

  throw new Error(
    'Missing STRIPE_SECRET_KEY environment variable. Set it to your Stripe secret key.'
  );
}

export function resolveBaseUrl(env = process.env) {
  for (const variable of BASE_URL_CANDIDATES) {
    const value = env?.[variable];
    if (value) {
      return value.replace(/\/$/, '');
    }
  }

  return 'http://localhost:5000';
}
