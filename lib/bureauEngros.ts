import fs from 'fs';
import path from 'path';

const ROOT_DIR = process.cwd();

const BUREAU_EN_GROS_OUTPUT_DIR = path.join(
  ROOT_DIR,
  'outputs',
  'bureauengros' // ❗ this must match the real folder name on disk
);

export function listBureauEnGrosStoreSlugs(): string[] {
  if (!fs.existsSync(BUREAU_EN_GROS_OUTPUT_DIR)) {
    console.warn('Bureau en Gros output dir does not exist:', BUREAU_EN_GROS_OUTPUT_DIR);
    return [];
  }

  return fs
    .readdirSync(BUREAU_EN_GROS_OUTPUT_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name);
}

export function readBureauEnGrosDeals(storeSlug: string): any[] | null {
  const jsonPath = path.join(BUREAU_EN_GROS_OUTPUT_DIR, storeSlug, 'data.json');

  if (!fs.existsSync(jsonPath)) {
    console.warn('❌ No Bureau en Gros data for slug:', storeSlug, 'at path:', jsonPath);
    return null;
  }

  try {
    const raw = fs.readFileSync(jsonPath, 'utf8');
    const parsed = JSON.parse(raw);

    if (Array.isArray(parsed)) {
      return parsed;
    }

    // If the scraper wrote an object with a "products" or "items" array, normalize it
    if (parsed && Array.isArray((parsed as any).products)) {
      return (parsed as any).products;
    }
    if (parsed && Array.isArray((parsed as any).items)) {
      return (parsed as any).items;
    }

    return [];
  } catch (error) {
    console.error('Failed to read Bureau en Gros JSON for slug:', storeSlug, error);
    return null;
  }
}
