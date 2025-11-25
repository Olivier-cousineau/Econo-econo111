import type { NextApiRequest, NextApiResponse } from 'next';
import { readBureauEnGrosDeals } from '../../../lib/bureauEnGros';

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  const { slug } = req.query;

  if (!slug || typeof slug !== 'string') {
    return res.status(400).json({ error: 'Missing slug' });
  }

  const data = readBureauEnGrosDeals(slug);
  res.status(200).json(data);
}
