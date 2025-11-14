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
import os from "os";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
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

function availableParallelism() {
  if (typeof os.availableParallelism === "function") {
    return os.availableParallelism();
  }
  const cpus = os.cpus?.();
  return Array.isArray(cpus) && cpus.length ? cpus.length : 1;
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: repoRoot,
      stdio: options.stdio ?? "inherit",
      env: { ...process.env, ...options.env },
    });

    child.on("close", (code, signal) => {
      resolve({ code, signal });
    });

    child.on("error", (error) => {
      console.error(`❌ Failed to start ${command}:`, error);
      resolve({ code: 1, error });
    });
  });
}

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

const DAY_NAME_TO_INDEX = {
  monday: 1,
  mon: 1,
  mardi: 2,
  tuesday: 2,
  tue: 2,
  mercredi: 3,
  wednesday: 3,
  wed: 3,
  jeudi: 4,
  thursday: 4,
  thu: 4,
  vendredi: 5,
  friday: 5,
  fri: 5,
  samedi: 6,
  saturday: 6,
  sat: 6,
  dimanche: 7,
  sunday: 7,
  sun: 7,
};

function parseShardInput(...values) {
  for (const value of values) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (!trimmed) continue;
      const lower = trimmed.toLowerCase();
      if (DAY_NAME_TO_INDEX[lower]) {
        return DAY_NAME_TO_INDEX[lower];
      }
      const numeric = parseNumeric(trimmed);
      if (numeric !== null) return numeric;
    } else if (typeof value === "number") {
      if (Number.isFinite(value)) return value;
    }
  }
  return null;
}

function toZeroBasedShard(oneBased, totalShards) {
  const fallback = 1;
  const input = Number.isFinite(oneBased) ? oneBased : fallback;
  const normalized = Math.max(1, Math.floor(input));
  return Math.min(totalShards - 1, normalized - 1);
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

const shards = parseNumeric(args.shards ?? args.parts ?? args.divide ?? 1);
const totalShards = Math.max(1, Math.floor(shards ?? 1));
if (totalShards > 1) {
  const shardInput = parseShardInput(
    args.shard,
    args.part,
    args.segment,
    args.slice,
    args.bucket,
    args.index,
    args.day,
    args.weekday,
    process.env.CT_SHARD,
    process.env.CT_SHARD_INDEX,
    process.env.CANADIANTIRE_SHARD,
    process.env.CANADIANTIRE_SHARD_INDEX,
    process.env.SHARD,
    process.env.SHARD_INDEX
  );

  const zeroBasedShard = toZeroBasedShard(shardInput, totalShards);
  const originalCount = stores.length;
  stores = stores.filter((_, idx) => idx % totalShards === zeroBasedShard);
  console.log(
    `🪓 Shard ${zeroBasedShard + 1}/${totalShards}: ${stores.length} store(s) out of ${originalCount}`
  );
  if (!stores.length) {
    console.error(
      `❌ No stores left after applying shard ${zeroBasedShard + 1}/${totalShards}. ` +
        `Check --shard/--shards arguments.`
    );
    process.exit(1);
  }
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

const scraperEntry = path.join(repoRoot, "scraper_ct.js");
const publishScript = path.join(repoRoot, "scripts", "publish_canadiantire_outputs.js");
const statusMap = new Map();
const publishedSlugs = [];
let gitQueue = Promise.resolve();

function runWithGitLock(task) {
  const next = gitQueue.then(() => task());
  gitQueue = next.catch(() => {});
  return next;
}

function storeLabel(store) {
  return store.city || store.name || "(inconnu)";
}

function getStatusKey(store, index) {
  return store.id ? String(store.id) : `idx-${index}`;
}

function setStatus(store, index, status, details = "") {
  const entry = {
    id: store.id ? String(store.id) : "?",
    city: storeLabel(store),
    status,
    details,
  };
  statusMap.set(getStatusKey(store, index), entry);
  return entry;
}

function getStatuses() {
  return stores.map((store, index) =>
    statusMap.get(getStatusKey(store, index)) ?? {
      id: store.id ? String(store.id) : "?",
      city: storeLabel(store),
      status: "pending",
      details: "",
    }
  );
}

async function summarizeStatuses() {
  const entries = getStatuses();
  const lines = [
    "## Canadian Tire shard summary",
    "",
    `Total stores: ${entries.length}`,
    "",
    "| # | Store ID | Ville | Statut | Détails |",
    "| - | - | - | - | - |",
  ];

  entries.forEach((entry, idx) => {
    lines.push(
      `| ${idx + 1} | ${entry.id} | ${entry.city || "(inconnu)"} | ${entry.status} | ${
        entry.details || ""
      } |`
    );
  });

  const summary = lines.join("\n");
  console.log(`\n${summary}\n`);
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (summaryPath) {
    fs.appendFileSync(summaryPath, `${summary}\n`);
  }
}

const maxConcurrentArg = parseNumeric(
  args["max-concurrent"] ??
    args.maxConcurrent ??
    args.parallel ??
    args.concurrency ??
    process.env.CT_MAX_CONCURRENT
);
const defaultParallelism = availableParallelism();
const maxConcurrent = Math.max(
  1,
  Math.min(stores.length, maxConcurrentArg ?? defaultParallelism)
);

async function processStore(store, index) {
  const cityLabel = storeLabel(store);
  if (!store.id || !cityLabel) {
    console.warn(`⚠️ Skipping invalid store entry: ${JSON.stringify(store)}`);
    setStatus(store, index, "skipped", "missing id or city");
    return { success: true };
  }

  console.log("\n==============================");
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
    setStatus(store, index, "skipped", "dry-run");
    return { success: true };
  }

  const scrape = await runCommand("node", scraperArgs);
  if (scrape.code !== 0) {
    const message = `scraper exited with code ${scrape.code}`;
    console.error(`❌ Scraper failed for store ${store.id}: ${message}`);
    setStatus(store, index, "failed", message);
    if (!continueOnError) {
      throw new Error(message);
    }
    return { success: false };
  }

  const slug = slugify(cityLabel, { lower: true, strict: true }) || "default";
  const storePath = path.join("outputs", "canadiantire", `${store.id}-${slug}`);
  const jsonPath = path.join(storePath, "data.json");

  if (!fs.existsSync(jsonPath)) {
    const message = `data.json not found at ${jsonPath}`;
    console.warn(`⚠️ ${message}`);
    setStatus(store, index, "skipped", message);
    return { success: false };
  }

  let rows = "?";
  try {
    const content = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
    rows = Array.isArray(content) ? String(content.length) : rows;
  } catch {
    rows = "?";
  }

  const gitOutcome = await runWithGitLock(async () => {
    console.log(`💾 Committing ${jsonPath}`);
    const gitAdd = await runCommand("git", ["add", jsonPath]);
    if (gitAdd.code !== 0) {
      return { stage: "add", code: gitAdd.code };
    }
    const commitMsg = `Canadian Tire: ${cityLabel} (${store.id}) – ${rows} produits`;
    const gitCommit = await runCommand("git", ["commit", "-m", commitMsg]);
    return { stage: "commit", code: gitCommit.code };
  });

  if (gitOutcome.stage === "add" && gitOutcome.code !== 0) {
    const message = `git add failed for ${jsonPath}`;
    console.error(`❌ ${message}`);
    setStatus(store, index, "failed", message);
    if (!continueOnError) {
      throw new Error(message);
    }
    return { success: false };
  }

  if (gitOutcome.stage === "commit" && gitOutcome.code !== 0 && gitOutcome.code !== 1) {
    const message = `git commit failed for ${cityLabel}`;
    console.error(`❌ ${message}`);
    setStatus(store, index, "failed", message);
    if (!continueOnError) {
      throw new Error(message);
    }
    return { success: false };
  }

  if (gitOutcome.stage === "commit" && gitOutcome.code === 1) {
    console.warn(`⚠️ git commit skipped for ${cityLabel} (store ${store.id})`);
    setStatus(store, index, "skipped", "nothing to commit");
    return { success: true };
  }

  setStatus(store, index, "committed", `${rows} produits`);
  publishedSlugs.push(slug || "default");
  return { success: true };
}

async function runAllStores() {
  console.log(`📦 Stores file: ${storesFile}`);
  console.log(`🧮 ${stores.length} store(s) to scrape`);
  if (dryRun)
    console.log("⚠️ Dry run mode: scrapes will be skipped, commits will not be created");
  if (!shouldPublish)
    console.log("ℹ️ Publication to data/canadian-tire disabled (--skip-publish)");
  console.log("\n📋 Stores in this shard:");
  stores.forEach((store, idx) => {
    console.log(`  ${idx + 1}. ${store.id ?? "?"} – ${storeLabel(store)}`);
  });
  console.log(`\n🚀 Running up to ${maxConcurrent} scraper(s) in parallel`);

  let cursor = 0;
  let encounteredError = false;

  async function worker() {
    while (true) {
      const index = cursor++;
      if (index >= stores.length) break;
      const store = stores[index];
      try {
        const result = await processStore(store, index);
        if (!result.success) {
          encounteredError = true;
        }
      } catch (error) {
        encounteredError = true;
        throw error;
      }
    }
  }

  const workers = Array.from({ length: Math.max(1, maxConcurrent) }, () => worker());
  try {
    await Promise.all(workers);
  } catch (error) {
    encounteredError = true;
    throw error;
  }
  return { encounteredError };
}

async function publishDatasets() {
  if (!shouldPublish || dryRun || !publishedSlugs.length) {
    return;
  }

  console.log("\n📤 Publishing normalized Canadian Tire feeds...");
  const publish = await runCommand("node", [publishScript]);
  if (publish.code !== 0) {
    console.error("❌ Failed to publish Canadian Tire datasets");
    if (!continueOnError) {
      throw new Error("publish failed");
    }
    return;
  }

  const uniqueSlugs = Array.from(new Set(publishedSlugs));
  const candidates = new Set(
    uniqueSlugs.map((slug) => path.join("data", "canadian-tire", `${slug}.json`))
  );
  candidates.add(path.join("data", "canadian-tire", "stores_with_data.json"));

  const existingFiles = Array.from(candidates).filter((relativePath) =>
    fs.existsSync(path.join(repoRoot, relativePath))
  );

  if (!existingFiles.length) {
    return;
  }

  const gitAdd = await runCommand("git", ["add", ...existingFiles]);
  if (gitAdd.code !== 0) {
    console.error("❌ git add failed while staging published datasets");
    if (!continueOnError) {
      throw new Error("git add failed for published datasets");
    }
    return;
  }

  const publishMsg =
    uniqueSlugs.length === 1
      ? `Canadian Tire: publish dataset for ${uniqueSlugs[0]}`
      : `Canadian Tire: publish datasets for ${uniqueSlugs.length} stores`;
  const gitCommit = await runCommand("git", ["commit", "-m", publishMsg]);
  if (gitCommit.code !== 0 && gitCommit.code !== 1) {
    console.error("❌ git commit failed for published datasets");
    if (!continueOnError) {
      throw new Error("git commit failed for published datasets");
    }
  }
}

async function main() {
  let encounteredError = false;
  try {
    const result = await runAllStores();
    encounteredError = result.encounteredError;
    await publishDatasets();
    console.log("\n✅ Done");
    if (encounteredError && !continueOnError) {
      process.exit(1);
    }
    if (encounteredError && continueOnError) {
      process.exitCode = 1;
    }
  } finally {
    try {
      await summarizeStatuses();
    } catch (error) {
      console.error("⚠️ Failed to write summary:", error);
    }
  }
}

await main().catch((error) => {
  console.error(error?.message ?? error);
  process.exit(1);
});
