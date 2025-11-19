#!/usr/bin/env node
// @ts-check
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.join(__dirname, '..');
const outputsRoot = path.join(repoRoot, 'outputs', 'canadiantire');
const statsDir = path.join(outputsRoot, 'index');
const statsFile = path.join(statsDir, 'stats.json');

/**
 * @returns {Promise<{ totalProducts: number; totalStores: number; updatedAt: string; }>}
 */
async function computeStats() {
  let dirEntries = [];
  try {
    dirEntries = await fs.promises.readdir(outputsRoot, { withFileTypes: true });
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      console.warn(`⚠️ Outputs directory not found at ${outputsRoot}`);
      return { totalProducts: 0, totalStores: 0, updatedAt: new Date().toISOString() };
    }
    throw error;
  }

  let totalProducts = 0;
  let totalStores = 0;

  for (const entry of dirEntries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const dataPath = path.join(outputsRoot, entry.name, 'data.json');
    if (!fs.existsSync(dataPath)) {
      continue;
    }

    try {
      const fileContents = await fs.promises.readFile(dataPath, 'utf-8');
      const parsed = JSON.parse(fileContents);
      const productsArray = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed?.products)
        ? parsed.products
        : [];
      const productCount = productsArray.length;

      if (productCount > 0) {
        totalStores += 1;
        totalProducts += productCount;
      }
    } catch (error) {
      console.warn(`⚠️ Unable to parse ${dataPath}:`, error);
    }
  }

  return { totalProducts, totalStores, updatedAt: new Date().toISOString() };
}

async function main() {
  const stats = await computeStats();
  await fs.promises.mkdir(statsDir, { recursive: true });
  await fs.promises.writeFile(statsFile, JSON.stringify(stats, null, 2));
  console.log(
    `📊 Canadian Tire stats updated: ${stats.totalProducts.toLocaleString()} produits dans ${stats.totalStores.toLocaleString()} magasins.`
  );
}

main().catch((error) => {
  console.error('❌ Failed to update Canadian Tire stats', error);
  process.exit(1);
});
