import { readCanadianTireStats } from '../../../lib/canadianTireStats';

export default async function handler(_req, res) {
  const stats = await readCanadianTireStats();
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate');
  res.status(200).json(stats);
}
