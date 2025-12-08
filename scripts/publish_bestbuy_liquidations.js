#!/usr/bin/env node
// @ts-check
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.join(__dirname, "..");

const SOURCE_PATH = path.join(repoRoot, "data", "bestbuy_liquidation.json");
const OUTPUT_DIR = path.join(repoRoot, "outputs", "bestbuy");
const OUTPUT_PATH = path.join(OUTPUT_DIR, "clearance.json");
const PUBLIC_BESTBUY_DIR = path.join(repoRoot, "public", "bestbuy");
const PUBLIC_OUTPUTS_DIR = path.join(repoRoot, "public", "outputs", "bestbuy");
const PUBLIC_BESTBUY_PATH = path.join(PUBLIC_BESTBUY_DIR, "clearance.json");
const PUBLIC_OUTPUTS_PATH = path.join(PUBLIC_OUTPUTS_DIR, "clearance.json");

function readSource() {
  if (!fs.existsSync(SOURCE_PATH)) {
    console.error(`❌ Fichier source introuvable: ${SOURCE_PATH}`);
    process.exit(1);
  }

  const raw = fs.readFileSync(SOURCE_PATH, "utf8");
  try {
    const data = JSON.parse(raw);
    if (!Array.isArray(data) || data.length === 0) {
      console.error("❌ Le fichier source ne contient aucun produit.");
      process.exit(1);
    }
    return data;
  } catch (error) {
    console.error("❌ Impossible de parser le JSON source:", error);
    process.exit(1);
  }
}

function toNumber(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const normalized = value.replace(/[^0-9,.-]/g, "").replace(/,(?=\d{2}\b)/g, ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatPriceRaw(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return `${value.toFixed(2)} $`;
}

function normalizeProduct(item) {
  if (!item || typeof item !== "object") return null;

  const title = String(
    item.product_name || item.title || item.name || item.product || ""
  ).trim();
  const url = String(item.product_link || item.url || "").trim();

  const sale = toNumber(item.sale_price ?? item.liquidation_price);
  const regular = toNumber(item.regular_price ?? item.price);
  const price = sale ?? regular ?? null;

  if (!title || !url || price === null) {
    return null;
  }

  return {
    title,
    url,
    price,
    price_raw: formatPriceRaw(price),
  };
}

function main() {
  const source = readSource();
  const normalized = source.map(normalizeProduct).filter(Boolean);

  if (!normalized.length) {
    console.error("❌ Aucun produit valide après normalisation.");
    process.exit(1);
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.mkdirSync(PUBLIC_BESTBUY_DIR, { recursive: true });
  fs.mkdirSync(PUBLIC_OUTPUTS_DIR, { recursive: true });

  const payload = JSON.stringify(normalized, null, 2);

  fs.writeFileSync(OUTPUT_PATH, payload);
  fs.writeFileSync(PUBLIC_BESTBUY_PATH, payload);
  fs.writeFileSync(PUBLIC_OUTPUTS_PATH, payload);

  console.log(
    `✅ ${normalized.length} produits publiés dans outputs/bestbuy/clearance.json`
  );
  console.log(`✅ Copie disponible sous public/bestbuy/clearance.json`);
  console.log(`✅ Copie disponible sous public/outputs/bestbuy/clearance.json`);
}

main();
