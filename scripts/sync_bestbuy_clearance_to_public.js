// scripts/sync_bestbuy_clearance_to_public.js
import fs from 'fs';
import path from 'path';

const ROOT_DIR = process.cwd();

const SOURCE_PATH = path.join(ROOT_DIR, 'outputs', 'bestbuy', 'clearance.json');
const TARGET_DIR = path.join(ROOT_DIR, 'public', 'bestbuy');
const TARGET_PATH = path.join(TARGET_DIR, 'clearance.json');

async function main() {
  try {
    if (!fs.existsSync(SOURCE_PATH)) {
      console.log('[BestBuy] Source file not found, skipping copy:', SOURCE_PATH);
      return;
    }

    await fs.promises.mkdir(TARGET_DIR, { recursive: true });
    await fs.promises.copyFile(SOURCE_PATH, TARGET_PATH);

    console.log('[BestBuy] Copied clearance.json to', TARGET_PATH);
  } catch (error) {
    console.error('[BestBuy] Failed to copy BestBuy clearance JSON', error);
    process.exitCode = 1;
  }
}

main();
