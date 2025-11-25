import type { NextApiRequest, NextApiResponse } from 'next';
import { readBureauEnGrosStoreDeals } from '../../../../lib/bureauEnGrosDeals';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const slugParam =
    Array.isArray(req.query.storeSlug)
      ? req.query.storeSlug[0]
      : req.query.storeSlug ?? (Array.isArray(req.query.slug) ? req.query.slug[0] : req.query.slug);
  const slug = typeof slugParam === 'string' ? slugParam.trim() : '';

  if (!slug) {
    res.status(400).json({ error: 'Missing store slug' });
    return;
  }

  try {
    const data = await readBureauEnGrosStoreDeals(slug);
    if (!data) {
      res.status(404).json({ error: 'Store not found or unavailable' });
      return;
    }
    res.status(200).json(data);
  } catch (error) {
    console.error('Failed to load Bureau en Gros deals', error);
    res.status(500).json({ error: 'Unable to load store data' });
  }
}
