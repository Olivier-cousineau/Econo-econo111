import fs from 'fs';
import path from 'path';

const ROOT_DIR = process.cwd();
const BUREAU_EN_GROS_OUTPUT_DIR = path.join(ROOT_DIR, 'outputs', 'bureauengros');

function readBureauEnGrosStoreDeals(storeSlug) {
  const storeDir = path.join(BUREAU_EN_GROS_OUTPUT_DIR, storeSlug);
  const jsonPath = path.join(storeDir, 'data.json');

  if (!fs.existsSync(jsonPath)) {
    return null;
  }

  try {
    const raw = fs.readFileSync(jsonPath, 'utf8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (error) {
    console.error(`Failed to read Bureau en Gros deals for slug: ${storeSlug}`, error);
    return null;
  }
}

export default async function handler(req, res) {
  const storeSlug = String(req.query.storeSlug || req.query.store || req.query.slug || '');

  if (!storeSlug) {
    return res.status(400).json({ error: 'Missing storeSlug' });
  }

  try {
    const data = readBureauEnGrosStoreDeals(storeSlug);

    if (!data) {
      res.status(404).json({ error: 'Store not found or unavailable' });
      return;
    }

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
