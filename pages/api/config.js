const PUBLISHABLE_KEY_CANDIDATES = [
  'STRIPE_PUBLISHABLE_KEY',
  'NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY',
  'STRIPE_PUBLIC_KEY',
];

function resolvePublishableKey() {
  for (const variable of PUBLISHABLE_KEY_CANDIDATES) {
    const value = process.env[variable];
    if (value) {
      return value;
    }
  }

  return null;
}

export default function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  const publishableKey = resolvePublishableKey();

  if (!publishableKey) {
    return res.status(500).json({
      error:
        'Missing STRIPE_PUBLISHABLE_KEY or NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY environment variable.',
    });
  }

  return res.status(200).json({ publishableKey });
}
