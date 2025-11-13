#!/usr/bin/env node
// @ts-check
/**
 * Run the Canadian Tire scraper for every store listed in a matrix file
 * and commit the resulting JSON for each city as soon as it is generated.
 *
 * Usage:
 *   node scripts/run_canadiantire_matrix.js [--file data/canadian-tire/branches.json]
 *                                           [--stores 271,649]
 *                                           [--limit 5]
 *                                           [--maxPages 80]
 *                                           [--dry-run]
 *                                           [--publish] [--skip-publish]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawnSync } from "child_process";
import minimist from "minimist";
import slugify from "slugify";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.join(__dirname, "..");

const args = minimist(process.argv.slice(2), {
  string: ["file", "stores", "maxPages"],
  boolean: ["dry-run", "dryRun", "continue", "publish"],
  alias: { dryRun: "dry-run" },
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

const storesFile = args.file || path.join("data", "canadian-tire", "branches.json");
if (!fs.existsSync(storesFile)) {
  console.error(`❌ Stores file not found: ${storesFile}`);
  process.exit(1);
}

/**
 * @typedef {{ id: string, name?: string, city?: string }} Store
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
  const wanted = new Set(filterIds);
  stores = stores.filter((store) => wanted.has(String(store.id)));
  if (!stores.length) {
    console.error(`❌ None of the requested stores (${filterIds.join(", ")}) were found.`);
    process.exit(1);
  }
}

const limit = Number(args.limit ?? args.count ?? args.n ?? 0);
if (Number.isFinite(limit) && limit > 0) {
  stores = stores.slice(0, limit);
}

const dryRun = parseBooleanArg(args["dry-run"] ?? args.dryRun, false);
const continueOnError = parseBooleanArg(args.continue ?? args["continue-on-error"], false);

const skipPublishArg = args["skip-publish"] ?? args.skipPublish ?? args["no-publish"];
let shouldPublish = true;
if (args.publish !== undefined) {
  shouldPublish = parseBooleanArg(args.publish, true);
} else if (skipPublishArg !== undefined) {
  shouldPublish = !parseBooleanArg(skipPublishArg, false);
}

const extraScraperArgs = [];
if (args.maxPages) {
  extraScraperArgs.push("--maxPages", String(args.maxPages));
}
if (parseBooleanArg(args.headful, false)) {
  extraScraperArgs.push("--headful");
}
const passthrough = [
  { key: "include-regular-price", flag: "--include-regular-price" },
  { key: "includeRegularPrice", flag: "--includeRegularPrice" },
  { key: "include-liquidation-price", flag: "--include-liquidation-price" },
  { key: "includeLiquidationPrice", flag: "--includeLiquidationPrice" },
];
for (const { key, flag } of passthrough) {
  if (key in args) {
    extraScraperArgs.push(flag, String(args[key]));
  }
}

console.log(`📦 Stores file: ${storesFile}`);
console.log(`🧮 ${stores.length} store(s) to scrape`);
if (dryRun) console.log("⚠️ Dry run mode: scrapes will be skipped, commits will not be created");
if (!shouldPublish) console.log("ℹ️ Publication to data/canadian-tire disabled (--skip-publish)");

const scraperEntry = path.join(repoRoot, "scraper_ct.js");
const publishScript = path.join(repoRoot, "scripts", "publish_canadiantire_outputs.js");
const publishedSlugs = [];

for (const store of stores) {
  const cityLabel = store.city || store.name || "";
  if (!store.id || !cityLabel) {
    console.warn(`⚠️ Skipping invalid store entry: ${JSON.stringify(store)}`);
    continue;
  }

  console.log(`\n==============================`);
  console.log(`🏬 Scraping store ${store.id} – ${cityLabel}`);

  const scraperArgs = [
    scraperEntry,
    "--store",
    String(store.id),
    "--city",
    cityLabel,
    ...extraScraperArgs,
  ];

  if (dryRun) {
    console.log(`(dry-run) node ${scraperArgs.join(" ")}`);
  } else {
    const scrape = spawnSync("node", scraperArgs, { stdio: "inherit" });
    if (scrape.status !== 0) {
      console.error(`❌ Scraper failed for store ${store.id}`);
      if (!continueOnError) {
        process.exit(scrape.status ?? 1);
      }
      continue;
    }
  }

  const slug = slugify(cityLabel, { lower: true, strict: true }) || "default";
  const storePath = path.join("outputs", "canadiantire", `${store.id}-${slug}`);
  const jsonPath = path.join(storePath, "data.json");

  if (!fs.existsSync(jsonPath)) {
    console.warn(`⚠️ No data.json found at ${jsonPath}`);
    continue;
  }

  if (dryRun) {
    console.log(`(dry-run) would commit ${jsonPath}`);
    continue;
  }

  console.log(`💾 Committing ${jsonPath}`);
  const gitAdd = spawnSync("git", ["add", jsonPath], { stdio: "inherit" });
  if (gitAdd.status !== 0) {
    console.error(`❌ git add failed for ${jsonPath}`);
    if (!continueOnError) process.exit(gitAdd.status ?? 1);
    continue;
  }

  let rows = "?";
  try {
    const content = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
    rows = Array.isArray(content) ? String(content.length) : rows;
  } catch {
    rows = "?";
  }

  const commitMsg = `Canadian Tire: ${cityLabel} (${store.id}) – ${rows} produits`;
  const gitCommit = spawnSync("git", ["commit", "-m", commitMsg], { stdio: "inherit" });
  if (gitCommit.status !== 0) {
    console.warn(`⚠️ git commit skipped for ${cityLabel} (store ${store.id})`);
    if (!continueOnError && gitCommit.status !== 1) {
      process.exit(gitCommit.status ?? 1);
    }
  }

  if (!dryRun) {
    publishedSlugs.push(slug || "default");
  }
}

if (shouldPublish && !dryRun && publishedSlugs.length) {
  console.log("\n📤 Publishing normalized Canadian Tire feeds...");
  const publish = spawnSync("node", [publishScript], { stdio: "inherit" });
  if (publish.status !== 0) {
    console.error("❌ Failed to publish Canadian Tire datasets");
    if (!continueOnError) process.exit(publish.status ?? 1);
  } else {
    const uniqueSlugs = Array.from(new Set(publishedSlugs));
    const candidates = new Set(
      uniqueSlugs.map((slug) => path.join("data", "canadian-tire", `${slug}.json`))
    );
    candidates.add(path.join("data", "canadian-tire", "stores_with_data.json"));

    const existingFiles = Array.from(candidates).filter((relativePath) =>
      fs.existsSync(path.join(repoRoot, relativePath))
    );

    if (existingFiles.length) {
      const gitAdd = spawnSync("git", ["add", ...existingFiles], { stdio: "inherit" });
      if (gitAdd.status !== 0) {
        console.error("❌ git add failed while staging published datasets");
        if (!continueOnError) process.exit(gitAdd.status ?? 1);
      } else {
        const publishMsg =
          uniqueSlugs.length === 1
            ? `Canadian Tire: publish dataset for ${uniqueSlugs[0]}`
            : `Canadian Tire: publish datasets for ${uniqueSlugs.length} stores`;
        const gitCommit = spawnSync("git", ["commit", "-m", publishMsg], { stdio: "inherit" });
        if (gitCommit.status !== 0 && gitCommit.status !== 1) {
          console.error("❌ git commit failed for published datasets");
          if (!continueOnError) process.exit(gitCommit.status ?? 1);
        }
      }
    }
  }
}

console.log("\n✅ Done");
