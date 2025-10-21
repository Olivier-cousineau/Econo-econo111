import Stripe from 'stripe';

const PLAN_CONFIG = {
  essential: {
    amount: 999,
    defaultName: 'Essential plan',
    defaultDescription: 'Essential access to the clearance intelligence feed.',
  },
  advanced: {
    amount: 1999,
    defaultName: 'Advanced plan',
    defaultDescription: 'Unlimited catalog access with real-time alerts.',
  },
  premium: {
    amount: 2999,
    defaultName: 'Premium plan',
    defaultDescription: 'Full AI optimisation suite for scaling resellers.',
  },
};

const SUPPORTED_LOCALES = new Set([
  'da',
  'de',
  'en',
  'es',
  'fi',
  'fr',
  'it',
  'ja',
  'nb',
  'nl',
  'pl',
  'pt',
  'sv',
]);

let cachedStripe = null;
let cachedSecretKey = null;

function resolveStripeSecretKey() {
  const candidates = [
    'STRIPE_SECRET_KEY',
    'STRIPE_SECRET',
    'STRIPE_API_KEY',
  ];

  for (const variable of candidates) {
    const value = process.env[variable];
    if (value) {
      return value;
    }
  }

  throw new Error(
    'Missing STRIPE_SECRET_KEY environment variable. Set it to your Stripe secret key.'
  );
}

function getStripeClient() {
  const secretKey = resolveStripeSecretKey();

  if (!cachedStripe || cachedSecretKey !== secretKey) {
    cachedStripe = new Stripe(secretKey, {
      apiVersion: process.env.STRIPE_API_VERSION || '2022-11-15',
    });
    cachedSecretKey = secretKey;
  }

  return cachedStripe;
}

function normaliseLocale(input) {
  if (!input) {
    return 'en';
  }

  const value = String(input).split('-')[0].toLowerCase();
  return SUPPORTED_LOCALES.has(value) ? value : 'en';
}

function resolveBaseUrl() {
  const candidates = [
    process.env.STRIPE_BASE_URL,
    process.env.NEXT_PUBLIC_APP_URL,
    process.env.NEXT_PUBLIC_SITE_URL,
    process.env.SITE_URL,
  ];

  for (const candidate of candidates) {
    if (candidate) {
      return candidate.replace(/\/$/, '');
    }
  }

  return 'http://localhost:5000';
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  let stripe;
  try {
    stripe = getStripeClient();
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }

  const payload = req.body && typeof req.body === 'object' ? req.body : {};
  const planKey = payload.plan;
  const planConfig = planKey ? PLAN_CONFIG[planKey] : null;

  if (!planConfig) {
    return res.status(400).json({ error: 'Unknown pricing plan.' });
  }

  const locale = normaliseLocale(payload.locale);
  const name = (payload.name || planConfig.defaultName || '').toString().trim();
  const description = (payload.description || planConfig.defaultDescription || '')
    .toString()
    .trim();

  const baseUrl = resolveBaseUrl();
  const successUrl =
    process.env.STRIPE_SUCCESS_URL ||
    `${baseUrl}/success?session_id={CHECKOUT_SESSION_ID}`;
  const cancelUrl = process.env.STRIPE_CANCEL_URL || `${baseUrl}/cancel`;

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      payment_method_types: ['card'],
      allow_promotion_codes: true,
      locale,
      success_url: successUrl,
      cancel_url: cancelUrl,
      automatic_tax: { enabled: false },
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: 'cad',
            unit_amount: planConfig.amount,
            product_data: {
              name: name || planConfig.defaultName,
              description: description || planConfig.defaultDescription,
            },
          },
        },
      ],
    });

    return res.status(200).json({ sessionId: session.id });
  } catch (error) {
    const statusCode = error && error.statusCode ? error.statusCode : 500;
    const message =
      (error && error.raw && error.raw.message) ||
      (error && error.message) ||
      'Unable to create Stripe Checkout session.';

    return res.status(statusCode >= 400 && statusCode < 600 ? statusCode : 500).json({
      error: message,
    });
  }
}
