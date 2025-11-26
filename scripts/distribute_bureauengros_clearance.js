#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import slugify from "slugify";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const repoRoot = path.join(__dirname, "..");
const MASTER_PATH = path.join(
  repoRoot,
  "outputs",
  "bureauengros",
  "clearance",
  "data.json",
);
const BRANCHES_PATH = path.join(
  repoRoot,
  "data",
  "bureauengros",
  "branches.json",
);

function ensureFile(filePath, label) {
  if (!fs.existsSync(filePath)) {
    console.error(`❌ Missing ${label}: ${filePath}`);
    process.exit(1);
  }
}

function readJson(filePath, label) {
  try {
    const content = fs.readFileSync(filePath, "utf8");
    return JSON.parse(content);
  } catch (error) {
    console.error(`❌ Failed to read ${label} at ${filePath}:`, error);
    process.exit(1);
  }
}

function slugifyStore(store) {
  const nameSource = store?.name ?? "store";
  const slugName = slugify(nameSource, { lower: true, strict: true });
  const idPart = String(store?.id ?? "").trim();
  return idPart ? `${idPart}-${slugName}` : slugName;
}

function writeStoreOutput(store, products) {
  const folder = path.join(
    __dirname,
    "..",
    "outputs",
    "bureauengros",
    slugifyStore(store),
  );
  fs.mkdirSync(folder, { recursive: true });

  const payload = {
    store,
    products,
  };

  const outputPath = path.join(folder, "data.json");
  fs.writeFileSync(outputPath, JSON.stringify(payload, null, 2), "utf8");
  console.log(
    `📝 Wrote ${products.length} clearance products for ${store?.name || "store"} to ${outputPath}`,
  );
}

function main() {
  if (!fs.existsSync(MASTER_PATH)) {
    console.warn(
      `⚠️ No national clearance data found at ${MASTER_PATH}, nothing to distribute.`,
    );
    process.exit(0);
  }

  ensureFile(BRANCHES_PATH, "branches.json");

  const master = readJson(MASTER_PATH, "national clearance data");
  const branches = readJson(BRANCHES_PATH, "branches list");

  if (!Array.isArray(branches)) {
    console.error("❌ branches.json must be an array of stores");
    process.exit(1);
  }

  const products = Array.isArray(master)
    ? master
    : Array.isArray(master?.products)
      ? master.products
      : [];
  if (!products.length) {
    console.warn(
      "⚠️ No products found in national clearance data; outputs will be empty.",
    );
  }

  branches.forEach((store) => {
    writeStoreOutput(store, products);
  });
}

main();
