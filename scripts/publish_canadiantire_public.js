#!/usr/bin/env node
// Copie tous les data.json de outputs/canadiantire vers public/canadiantire
// Exemple :
//   outputs/canadiantire/271-st-jerome-qc/data.json
// → public/canadiantire/271-st-jerome-qc.json

import { promises as fs } from "fs";
import path from "path";

async function main() {
  const outputsRoot = path.join("outputs", "canadiantire");
  const publicRoot = path.join("public", "canadiantire");

  // Crée le dossier public/canadiantire s'il n'existe pas
  await fs.mkdir(publicRoot, { recursive: true });

  let entries;
  try {
    entries = await fs.readdir(outputsRoot, { withFileTypes: true });
  } catch (err) {
    console.error("❌ Impossible de lire", outputsRoot, err.message);
    process.exit(1);
  }

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const storeSlug = entry.name; // ex: "271-st-jerome-qc"
    const src = path.join(outputsRoot, storeSlug, "data.json");
    const dest = path.join(publicRoot, `${storeSlug}.json`);

    try {
      // Vérifie que data.json existe
      await fs.access(src);
    } catch {
      console.log(`⚠️  Pas de data.json pour ${storeSlug}, on saute.`);
      continue;
    }

    try {
      const raw = await fs.readFile(src, "utf-8");

      // Vérifie que c'est du JSON valide (évite de déployer du contenu corrompu)
      JSON.parse(raw);

      await fs.writeFile(dest, raw);
      console.log(`✅ Copié ${src} → ${dest}`);
    } catch (err) {
      console.warn(`❌ Erreur pour ${storeSlug}: ${err.message}`);
    }
  }

  console.log("✨ Publication Canadian Tire vers public/ terminée.");
}

main().catch((err) => {
  console.error("❌ Erreur dans publish_canadiantire_public:", err);
  process.exit(1);
});
