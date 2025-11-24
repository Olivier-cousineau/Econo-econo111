import fs from 'fs';
import path from 'path';
import slugify from 'slugify';

const BRANCHES_PATH = path.join('data', 'bureauengros', 'branches.json');
const MASTER_PATH = path.join('outputs', 'bureauengros', 'clearance', 'data.json');

function ensureFileExists(filePath, label){
  if(!fs.existsSync(filePath)){
    console.error(`❌ Missing ${label} at ${filePath}`);
    process.exit(1);
  }
}

function buildSlug(branch){
  const id = String(branch.id ?? '').trim();
  const citySource = branch.city || branch.name || branch.store || '';
  const province = branch.province || '';
  const slugSource = [citySource, province].filter(Boolean).join(' ');
  const citySlug = slugify(slugSource || citySource || 'store', { lower: true, strict: true });
  return id ? `${id}-${citySlug}` : citySlug;
}

async function main(){
  ensureFileExists(BRANCHES_PATH, 'branches.json');
  ensureFileExists(MASTER_PATH, 'clearance data');

  const branchesRaw = await fs.promises.readFile(BRANCHES_PATH, 'utf-8');
  const masterRaw = await fs.promises.readFile(MASTER_PATH, 'utf-8');

  const branches = JSON.parse(branchesRaw);
  const products = JSON.parse(masterRaw);

  if(!Array.isArray(branches)){
    console.error('❌ Branches file is not an array');
    process.exit(1);
  }
  if(!Array.isArray(products)){
    console.error('❌ Master clearance data is not an array');
    process.exit(1);
  }

  for(const branch of branches){
    if(!branch) continue;
    const slug = buildSlug(branch);
    const storeDir = path.join('outputs', 'bureauengros', slug);
    const outputPath = path.join(storeDir, 'data.json');
    await fs.promises.mkdir(storeDir, { recursive: true });
    const enriched = products.map(product => ({
      ...product,
      storeId: branch.id || '',
      storeName: branch.name || '',
      city: branch.city || branch.name || '',
      province: branch.province || '',
      storeBrand: 'Bureau en Gros'
    }));
    await fs.promises.writeFile(outputPath, JSON.stringify(enriched, null, 2), 'utf-8');
    console.log(`📝 Wrote ${enriched.length} products to ${outputPath}`);
  }
}

main().catch((error) => {
  console.error('❌ Distribution failed', error);
  process.exit(1);
});
