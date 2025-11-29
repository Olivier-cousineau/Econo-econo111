// scripts/generate_bureauengros_outputs_from_saint_jerome.js
// Génère un dossier outputs/bureauengros/<slug>/data.json
// pour chaque magasin dans data/bureauengros/stores.json,
// en copiant les liquidations de saint-jerome.json.

const fs = require('fs');
const path = require('path');

const ROOT_DIR = process.cwd();

const STORES_PATH = path.join(ROOT_DIR, 'data', 'bureauengros', 'stores.json');
const MASTER_STORE_PATH = path.join(ROOT_DIR, 'data', 'bureauengros', 'saint-jerome.json');
const OUTPUT_ROOT = path.join(ROOT_DIR, 'outputs', 'bureauengros');

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function slugify(text) {
  return String(text)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

// name: "Bureau en Gros – Saint-Jérôme, QC", id: "124"
// => "124-bureau-en-gros-saint-jerome-qc"
function buildStoreSlug(store) {
  const id = String(store.id || store.storeId || '').trim();
  const name = String(store.name || '').trim();

  if (!id || !name) {
    throw new Error(`Store sans id ou name valide: ${JSON.stringify(store)}`);
  }

  const nameSlug = slugify(name);
  return `${id}-${nameSlug}`;
}

function main() {
  console.log('📦 Chargement des données Bureau en Gros...');

  if (!fs.existsSync(STORES_PATH)) {
    console.error(`❌ Fichier introuvable: ${STORES_PATH}`);
    process.exit(1);
  }
  if (!fs.existsSync(MASTER_STORE_PATH)) {
    console.error(`❌ Fichier introuvable: ${MASTER_STORE_PATH}`);
    process.exit(1);
  }

  const stores = JSON.parse(fs.readFileSync(STORES_PATH, 'utf8'));
  const masterData = JSON.parse(fs.readFileSync(MASTER_STORE_PATH, 'utf8'));

  console.log(`✅ ${stores.length} magasins trouvés dans stores.json`);
  console.log('📍 Magasin maître: saint-jerome.json');

  ensureDir(OUTPUT_ROOT);

  let ok = 0;
  let failed = 0;

  for (const store of stores) {
    try {
      const slug = buildStoreSlug(store);
      const storeDir = path.join(OUTPUT_ROOT, slug);
      ensureDir(storeDir);

      const outPath = path.join(storeDir, 'data.json');
      fs.writeFileSync(outPath, JSON.stringify(masterData, null, 2), 'utf8');

      console.log(`💾 Écrit: ${outPath}`);
      ok++;
    } catch (err) {
      console.error('⚠️ Erreur pour un magasin:', err.message);
      failed++;
    }
  }

  console.log(`\n✅ Terminé: ${ok} magasin(s) générés, ${failed} en erreur.`);
}

main();
