#!/usr/bin/env node
// @ts-check
/**
 * Scraper Canadian Tire - Liquidation (Playwright)
 */
import { chromium } from "playwright";
import fs from "fs-extra";
import path from "path";
import axios from "axios";
import pLimit from "p-limit";
import sanitize from "sanitize-filename";
import { createObjectCsvWriter } from "csv-writer";
import minimist from "minimist";
import { fileURLToPath } from "url";

const args = minimist(process.argv.slice(2));
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ------------- CLI -------------
const DEFAULT_STORE = "0271";
const storeArg =
  args.store !== undefined && args.store !== null && args.store !== ""
    ? String(args.store)
    : DEFAULT_STORE;
const DEFAULT_URL = `https://www.canadiantire.ca/fr/promotions/liquidation.html?store=${storeArg}`;
const START_URL = args.url || DEFAULT_URL;
const MAX_PAGES = Number(args.maxPages || 125);
const HEADLESS = !args.headful;

// ------------- CONFIG -------------
const DEFAULT_OUT_JSON = path.join(
  "data",
  "canadian-tire",
  "saint-jerome.json"
);
const resolvedOutJson = path.resolve(args.out || args.outJson || DEFAULT_OUT_JSON);
const outJsonExt = path.extname(resolvedOutJson) || ".json";
const outJsonBase = path.basename(resolvedOutJson, outJsonExt);
const outJsonDir = path.dirname(resolvedOutJson);

const OUT_JSON = resolvedOutJson;
const OUT_CSV = path.resolve(
  args.outCsv ||
    args.csv ||
    path.join(outJsonDir, `${outJsonBase}.csv`)
);
const OUT_DIR = path.resolve(
  args.imagesDir ||
    args.images ||
    args.outImages ||
    path.join(outJsonDir, `${outJsonBase}-images`)
);
const CONCURRENCY = 6;

const SELECTORS = {
  product: [
    "li[data-testid='product-grids'] article",
    "li[data-testid='product-grids']",
    "article[data-testid='product-tile']",
    "li[data-testid^='product-grid']",
    ".product-grid__item article",
  ].join(", "),
  title: [
    "[data-testid='product-title']",
    ".product-name",
    ".pdp-link",
    "h3, h2",
  ].join(", "),
  price: [
    "[data-testid='sale-price']",
    "[data-testid='product-price']",
    ".price__value, .sale-price__value, .product-price",
    ".price, .c-pricing__sale, .c-pricing__current",
  ].join(", "),
  badge: [
    ".badge--clearance",
    ".badge--liquidation",
    ".tag--clearance",
    "[data-testid='badge-clearance']",
  ].join(", "),
  image: [
    "img[data-testid='product-image']",
    ".product-image img",
    "img",
  ].join(", "),
  link: "a[href]",
};

const PAGINATION = {
  // conteneur de la grille (inchangé)
  waitForList: "ul[data-testid='product-grids'], .product-grid",

  // flèche "suivant" — plusieurs variantes possibles sur CT
  nextSelectors: [
    "nav[aria-label='Pagination'] a[aria-label='Next']:not(.pagination_chevron--disabled)",
    "nav[aria-label='Pagination'] button[aria-label='Next']:not([disabled])",
    "a[data-testid='chevron->']:not(.pagination_chevron--disabled)",
    "button:has-text('>'):not([disabled])",
    "a.pagination_chevron:not(.pagination_chevron--disabled)",
  ],

  loadMoreBtn: [
    "button[data-testid='load-more']",
    "button:has-text('Charger plus')",
    "button:has-text('Load more')",
  ].join(", "),
};

function nextBtn(page) {
  return page.locator(PAGINATION.nextSelectors.join(", ")).first();
}

// ------------- UTILS -------------
function extractPrice(text) {
  if (!text) return null;
  const m = text.replace(/\s/g, "").match(/([0-9]+(?:[.,][0-9]{2})?)/);
  if (!m) return null;
  const norm = m[1].replace(",", ".");
  const num = Number(norm);
  return Number.isFinite(num) ? num : null;
}

async function downloadImage(url, idx, title) {
  if (!url) return null;
  await fs.ensureDir(OUT_DIR);
  let ext = ".jpg";
  try {
    const u = new URL(url);
    const guess = path.extname(u.pathname).split("?")[0];
    if (guess) ext = guess;
  } catch (_) {}
  const name =
    sanitize(`${String(idx).padStart(4, "0")}-${(title || "product").slice(0, 40)}`) +
    ext;
  const outPath = path.join(OUT_DIR, name);
  const res = await axios.get(url, { responseType: "arraybuffer", timeout: 60000 });
  await fs.writeFile(outPath, res.data);
  return outPath;
}

async function scrapeListOnce(page) {
  const items = await page.$$eval(SELECTORS.product, (cards, SELECTORS) => {
    const pickText = (el, sel) => {
      const n = el.querySelector(sel);
      return n ? n.textContent.trim() : "";
    };
    const pickImg = (el, sel) => {
      const n = el.querySelector(sel);
      if (!n) return null;
      for (const a of ["src", "data-src", "data-original", "data-image", "srcset"]) {
        const v = n.getAttribute(a);
        if (v) {
          if (a === "srcset" && v.includes(",")) return new URL(v.split(",")[0].trim().split(" ")[0], location.href).toString();
          return new URL(v, location.href).toString();
        }
      }
      return null;
    };
    const pickHref = (el, sel) => {
      const a = el.querySelector(sel);
      return a ? new URL(a.getAttribute("href"), location.href).toString() : null;
    };

    return cards.map((el) => {
      const title = pickText(el, SELECTORS.title);
      const priceRaw = pickText(el, SELECTORS.price);
      const hasBadge = !!el.querySelector(SELECTORS.badge);
      const text = el.textContent || "";
      const liquidation =
        hasBadge ||
        /liquidation|clearance|soldes?/i.test(title) ||
        /liquidation|clearance|soldes?/i.test(text.slice(0, 400));
      const image = pickImg(el, SELECTORS.image);
      const url = pickHref(el, SELECTORS.link);

      return { title, price_raw: priceRaw, liquidation, image, url };
    });
  }, SELECTORS);

  for (const it of items) it.price = extractPrice(it.price_raw);
  return items.filter((p) => p.title || p.price || p.image);
}

async function maybeCloseStoreModal(page) {
  const selectors = [
    "button[aria-label='Fermer']",
    "button[aria-label='Close']",
    "button:has-text('Plus tard')",
    "button:has-text('Later')",
    "button:has-text('Continuer')",
    "button:has-text('Continue')",
  ];
  for (const sel of selectors) {
    try {
      const locator = page.locator(sel).first();
      const ok = await locator.isVisible().catch(() => false);
      if (ok) {
        await locator.click().catch(() => {});
        await page.waitForTimeout(500);
      }
    } catch {
      // ignore
    }
  }
}

// ------------- MAIN -------------
async function main() {
  const browser = await chromium.launch({
    headless: HEADLESS,
    args: ["--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({ locale: "fr-CA" });
  const page = await context.newPage();

  console.log("➡️  Go to:", START_URL);

  let retries = 3;
  while (retries > 0) {
    try {
      await page.goto(START_URL, { timeout: 120000, waitUntil: "domcontentloaded" });
      break;
    } catch (e) {
      retries--;
      if (retries === 0) throw e;
      console.log("Retrying page load...");
      await page.waitForTimeout(3000);
    }
  }

  await maybeCloseStoreModal(page);

  const all = [];
  let pageCount = 0;

  while (pageCount < MAX_PAGES) {
    pageCount += 1;
    try {
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 15000 });
    } catch {
      // continue anyway
    }

    const items = await scrapeListOnce(page);
    console.log(`✅ Page ${pageCount}: ${items.length} produits`);
    all.push(...items);

    if (pageCount % 10 === 0) await page.waitForTimeout(1500);

    const loadMore = page.locator(PAGINATION.loadMoreBtn).first();
    if (await loadMore.isVisible().catch(() => false)) {
      await Promise.all([
        loadMore.click({ delay: 30 }).catch(() => {}),
        page.waitForLoadState("domcontentloaded"),
      ]);
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(800);
      continue;
    }

    // ---- pagination: cliquer sur la flèche "suivant"
    const next = nextBtn(page);
    if (await next.isVisible().catch(() => false)) {
      const before = page.url();
      await next.click({ delay: 30 }).catch(() => {});
      await page.waitForLoadState("domcontentloaded");
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(800);

      // Si l'URL n'a pas bougé, on force un petit scroll pour déclencher le rendu
      if (page.url() === before) {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(800);
      }
      continue; // prochaine page
    }

    break; // plus de "suivant" visible → fin
  }

  const limit = pLimit(CONCURRENCY);
  let idx = 0;
  const withLocalImages = await Promise.all(
    all.map((p) =>
      limit(async () => {
        idx += 1;
        let image_path = null;
        if (p.image) {
          try {
            image_path = await downloadImage(p.image, idx, p.title);
          } catch {
            console.warn("⚠️  image download failed:", p.image);
          }
        }
        return { ...p, image_path };
      })
    )
  );

  await fs.ensureDir(outJsonDir);
  await fs.writeJson(OUT_JSON, withLocalImages, { spaces: 2 });
  console.log(`💾  JSON → ${OUT_JSON}`);

  await fs.ensureDir(path.dirname(OUT_CSV));

  const csv = createObjectCsvWriter({
    path: OUT_CSV,
    header: [
      { id: "title", title: "title" },
      { id: "price", title: "price" },
      { id: "price_raw", title: "price_raw" },
      { id: "liquidation", title: "liquidation" },
      { id: "url", title: "url" },
      { id: "image", title: "image" },
      { id: "image_path", title: "image_path" },
    ],
  });
  await csv.writeRecords(withLocalImages);
  console.log(`📄  CSV  → ${OUT_CSV}`);

  await browser.close();
}

main().catch((e) => {
  console.error("❌ Error:", e);
  process.exit(1);
});
