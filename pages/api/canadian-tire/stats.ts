import type { NextApiRequest, NextApiResponse } from 'next';
import { readCanadianTireStats } from '../../../lib/canadianTireStats';

export default async function handler(_req: NextApiRequest, res: NextApiResponse) {
  const stats = await readCanadianTireStats();
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate');
  res.status(200).json(stats);
}
