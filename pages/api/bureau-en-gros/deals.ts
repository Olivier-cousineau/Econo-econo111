import type { NextApiRequest, NextApiResponse } from 'next';
import { readBureauEnGrosStoreDeals } from '../../../lib/bureauEnGrosDeals';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const { slug } = req.query;

  if (!slug || typeof slug !== 'string') {
    return res.status(400).json({ error: 'Missing slug' });
  }

  try {
    const data = await readBureauEnGrosStoreDeals(slug);
    res.status(200).json({
      store: data.store,
      products: Array.isArray(data.products) ? data.products : [],
    });
  } catch (error) {
    console.error('Failed to load Bureau en Gros deals via dedicated API', error);
    res.status(500).json({ error: 'Unable to load store data' });
  }
}
