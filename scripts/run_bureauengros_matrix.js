#!/usr/bin/env node
// @ts-check
/**
 * Run the Bureau en Gros scraper for every store listed in a matrix file
 * with optional sharding support.
 *
 * Usage:
 *   node scripts/run_bureauengros_matrix.js [--file data/bureauengros/branches.json]
 *                                           [--stores 124,308]
 *                                           [--shards 40]
 *                                           [--shard 1]
 *                                           [--continue]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import minimist from "minimist";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.join(__dirname, "..");

const args = minimist(process.argv.slice(2), {
  string: ["file", "stores", "shards", "shard"],
  boolean: ["continue"],
});

function parseBooleanArg(value, defaultValue = false) {
  if (value === undefined) return defaultValue;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["false", "0", "no", "off"].includes(normalized)) return false;
    if (["true", "1", "yes", "on"].includes(normalized)) return true;
  }
  return defaultValue;
}

function parseNumeric(value) {
  if (value === undefined || value === null) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

const defaultMatrixFile = path.join("data", "bureauengros", "locations.json");
const fallbackMatrixFile = path.join("data", "bureauengros", "branches.json");
const storesFile =
  args.file || (fs.existsSync(defaultMatrixFile) ? defaultMatrixFile : fallbackMatrixFile);

if (!fs.existsSync(storesFile)) {
  console.error(`❌ Stores file not found: ${storesFile}`);
  process.exit(1);
}

/**
 * @typedef {{ id: string | number, name?: string, city?: string }} Store
 */
const raw = JSON.parse(fs.readFileSync(storesFile, "utf8"));
let stores = Array.isArray(raw) ? raw : raw?.stores || [];
if (!Array.isArray(stores) || stores.length === 0) {
  console.error(`❌ No stores found inside ${storesFile}`);
  process.exit(1);
}

const filterIds = (args.stores || "")
  .split(/[,\s]+/)
  .map((s) => s.trim())
  .filter(Boolean);
if (filterIds.length) {
  const wanted = new Set(filterIds.map(String));
  stores = stores.filter((store) => wanted.has(String(store.id)));
  if (!stores.length) {
    console.error(`❌ None of the requested stores (${filterIds.join(", ")}) were found.`);
    process.exit(1);
  }
}

const shardIndexInput = parseNumeric(args.shard ?? args.shardIndex ?? args["shard-index"]);
const shardTotalInput = parseNumeric(args.shards ?? args.shardTotal ?? args["shard-total"]);
const shardTotal = Math.max(1, Math.floor(shardTotalInput ?? 40));

if (shardIndexInput !== null) {
  const shardIndex = Math.floor(shardIndexInput);
  if (!Number.isFinite(shardIndex) || shardIndex < 1 || shardIndex > shardTotal) {
    console.error(
      `❌ Invalid shard index ${shardIndexInput}. Expected a value between 1 and ${shardTotal}.`
    );
    process.exit(1);
  }

  const filteredStores = stores.filter((_, index) => {
    const shardNumber = (index % shardTotal) + 1;
    return shardNumber === shardIndex;
  });

  console.log(`Running Bureau en Gros shard ${shardIndex}/${shardTotal} with ${filteredStores.length} stores`);

  if (!filteredStores.length) {
    console.error("❌ No stores left after applying shard filter.");
    process.exit(1);
  }

  stores = filteredStores;
}

const continueOnError = parseBooleanArg(args.continue, false);
const scraperScript = path.join(repoRoot, "scripts", "scraper_bureauengros_clearance.js");

if (!fs.existsSync(scraperScript)) {
  console.error(`❌ Bureau en Gros scraper not found: ${scraperScript}`);
  process.exit(1);
}

function formatStoreLabel(store) {
  return store.name || store.city || "(unknown)";
}

function runStore(store) {
  return new Promise((resolve, reject) => {
    const storeId = String(store.id ?? "").trim() || "(unknown)";
    console.log(`Scraping Bureau en Gros store ${storeId} – ${formatStoreLabel(store)}`);

    const child = spawn("node", [scraperScript, "--storeId", storeId], {
      stdio: "inherit",
      cwd: repoRoot,
      env: process.env,
    });

    child.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        console.error(`❌ Failed to scrape store ${storeId} (exit code ${code})`);
        reject(new Error(`Store ${storeId} failed with code ${code}`));
      }
    });

    child.on("error", (error) => {
      console.error(`❌ Failed to start scraper for store ${storeId}:`, error);
      reject(error);
    });
  });
}

async function main() {
  const CONCURRENCY = 2;
  let hadFailures = false;

  for (let i = 0; i < stores.length; i += CONCURRENCY) {
    const batch = stores.slice(i, i + CONCURRENCY);

    try {
      await Promise.all(batch.map(runStore));
    } catch (error) {
      console.error(String(error));
      hadFailures = true;
      if (!continueOnError) {
        process.exit(1);
      }
    }
  }

  if (hadFailures) {
    process.exit(1);
  }
}

main();
