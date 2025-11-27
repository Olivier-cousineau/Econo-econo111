import fs from 'fs';
import path from 'path';

const ROOT_DIR = process.cwd();

// 🔹 Single source file for ALL Bureau en Gros locations
const BUREAU_EN_GROS_SOURCE_FILE = path.join(
  ROOT_DIR,
  'data',
  'bureauengros',
  'saint-jerome.json'
);

// 🔹 Directory that contains all Bureau en Gros store folders
const BUREAU_EN_GROS_OUTPUT_DIR = path.join(
  ROOT_DIR,
  'outputs',
  'bureauengros'
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

// 🔹 Always return the same deals for all stores (based on saint-jerome.json)
export function readBureauEnGrosDealsForAllStores(): any[] {
  if (!fs.existsSync(BUREAU_EN_GROS_SOURCE_FILE)) {
    console.error('❌ Source file for Bureau en Gros not found:', BUREAU_EN_GROS_SOURCE_FILE);
    return [];
  }

  try {
    const raw = fs.readFileSync(BUREAU_EN_GROS_SOURCE_FILE, 'utf8');
    const parsed = JSON.parse(raw);

    if (Array.isArray(parsed)) {
      return parsed;
    }

    if (parsed && Array.isArray((parsed as any).products)) {
      return (parsed as any).products;
    }

    if (parsed && Array.isArray((parsed as any).items)) {
      return (parsed as any).items;
    }

    return [];
  } catch (error) {
    console.error('Failed to read Bureau en Gros JSON from saint-jerome.json', error);
    return [];
  }
}
