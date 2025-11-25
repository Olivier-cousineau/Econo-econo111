import type { NextApiRequest, NextApiResponse } from 'next';
import { readBureauEnGrosStoreDeals } from '../../../lib/bureauEnGrosDeals';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const storeSlug = String(req.query.storeSlug || req.query.store || req.query.slug || '');

  if (!storeSlug) {
    return res.status(400).json({ error: 'Missing storeSlug' });
  }

  try {
    const data = await readBureauEnGrosStoreDeals(storeSlug);
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate');
    res.status(200).json({
      store: data.store ?? null,
      products: Array.isArray(data.products) ? data.products : [],
    });
  } catch (error) {
    console.error('Failed to load Bureau en Gros deals via dedicated API', error);
    res.status(500).json({ error: 'Unable to load store data' });
  }
}
