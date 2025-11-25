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

function getStoreSlug(query) {
  const slugCandidate = query.storeSlug ?? query.slug ?? query.branchSlug ?? query.branch;
  const slug = Array.isArray(slugCandidate) ? slugCandidate[0] : slugCandidate;
  return typeof slug === 'string' ? slug.trim() : '';
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const retailer = typeof req.query.retailer === 'string' ? req.query.retailer.toLowerCase() : '';
  const storeSlug = getStoreSlug(req.query);

  if (!retailer) {
    res.status(400).json({ error: 'Missing retailer' });
    return;
  }

  if (retailer === 'bureauengros' || retailer === 'bureau-en-gros') {
    if (!storeSlug) {
      res.status(400).json({ error: 'Missing store slug' });
      return;
    }

    try {
      const data = readBureauEnGrosStoreDeals(storeSlug);
      if (!data) {
        res.status(404).json({ error: 'Store not found or unavailable' });
        return;
      }
      res.status(200).json(data);
    } catch (error) {
      console.error('Failed to load Bureau en Gros deals via generic API', error);
      res.status(500).json({ error: 'Unable to load store data' });
    }
    return;
  }

  res.status(400).json({ error: `Unsupported retailer: ${retailer}` });
}
