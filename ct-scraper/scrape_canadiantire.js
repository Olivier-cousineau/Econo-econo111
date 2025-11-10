#!/usr/bin/env node
/**
 * Scraper Canadian Tire - Liquidation (Playwright)
 * - Parcourt les pages de liquidation (ou une catégorie liquidation)
 * - Extrait: title, price, image, product url, liquidation flag
 * - Télécharge les images ./images/
 * - Sauvegarde data.json + data.csv
 *
 * Lancer:
 *   node scrape_canadiantire.js --url "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271"
 *
 * Options:
 *   --url        URL de la page de liquidation (avec store=XXX recommandé)
 *   --maxPages   nb max de pages à parcourir (défaut 20)
 *   --headful    pour voir le navigateur (défaut headless)
 */

const { chromium } = require("playwright");
const fs = require("fs-extra");
const path = require("path");
const axios = require("axios");
const pLimit = require("p-limit");
const sanitize = require("sanitize-filename");
const { createObjectCsvWriter } = require("csv-writer");

// ------------- CLI -------------
const args = require("minimist")(process.argv.slice(2));
const START_URL =
  args.url ||
  "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271"; // St-Jérôme par défaut
const MAX_PAGES = Number(args.maxPages || 20);
const HEADLESS = !args.headful;

// ------------- CONFIG -------------
const OUT_DIR = "./images";
const OUT_JSON = "./data.json";
const OUT_CSV = "./data.csv";
const CONCURRENCY = 6;

const SELECTORS = {
  // Conteneur tuile produit (plusieurs variantes vues sur CT)
  product: [
    "li[data-testid='product-grids'] article",
    "li[data-testid='product-grids']",
    "article[data-testid='product-tile']",
    "li[data-testid^='product-grid']",
    ".product-grid__item article",
  ].join(", "),
  // Titre
  title: [
    "[data-testid='product-title']",
    ".product-name",
    ".pdp-link",
    "h3, h2",
  ].join(", "),
  // Prix (sale ou current)
  price: [
    "[data-testid='sale-price']",
    "[data-testid='product-price']",
    ".price__value, .sale-price__value, .product-price",
    ".price, .c-pricing__sale, .c-pricing__current",
  ].join(", "),
  // Badge liquidation / texte
  badge: [
    ".badge--clearance",
    ".badge--liquidation",
    ".tag--clearance",
    "[data-testid='badge-clearance']",
  ].join(", "),
  // Image
  image: ["img[data-testid='product-image']", ".product-image img", "img"].join(", "),
  // Lien
  link: "a[href]",
};

// Pagination: CT utilise souvent “Charger plus” ou une pagination flèche
const PAGINATION = {
  loadMoreBtn: [
    "button[data-testid='load-more']",
    "button:has-text('Charger plus')",
    "button:has-text('Load more')",
  ].join(", "),
  nextBtn: [
    "a[aria-label='Next']:not(.pagination_chevron--disabled)",
    "a[data-testid='chevron->']:not(.pagination_chevron--disabled')",
    "a[rel='next']:not(.disabled)",
  ].join(", "),
  waitForList: ["ul[data-testid='product-grids']", ".product-grid"].join(", "),
};

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
  const res = await axios.get(url, {
    responseType: "arraybuffer",
    timeout: 60000,
  });
  await fs.writeFile(outPath, res.data);
  return outPath;
}

async function scrapeListOnce(page) {
  const items = await page.$$eval(
    SELECTORS.product,
    (cards, SELECTORS) => {
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
            if (a === "srcset" && v.includes(","))
              return new URL(v.split(",")[0].trim().split(" ")[0], location.href).toString();
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
    },
    SELECTORS
  );

  for (const it of items) it.price = extractPrice(it.price_raw);
  return items.filter((p) => p.title || p.price || p.image);
}

async function maybeCloseStoreModal(page) {
  // Fermer une modale de sélection de magasin si elle apparaît
  const selectors = [
    "button[aria-label='Fermer']",
    "button[aria-label='Close']",
    "button:has-text('Plus tard')",
    "button:has-text('Later')",
    "button:has-text('Continuer')",
  ];
  for (const sel of selectors) {
    const ok = await page.locator(sel).first().isVisible().catch(() => false);
    if (ok) {
      await page.click(sel).catch(() => {});
      break;
    }
  }
}

async function main() {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ locale: "fr-CA" });
  const page = await context.newPage();

  console.log("➡️  Go to:", START_URL);
  await page.goto(START_URL, { timeout: 120000, waitUntil: "domcontentloaded" });
  await maybeCloseStoreModal(page);

  const all = [];
  let pageCount = 0;

  while (pageCount < MAX_PAGES) {
    pageCount += 1;
    try {
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 15000 });
    } catch {
      /* continue quand même */
    }

    const items = await scrapeListOnce(page);
    console.log(`✅ Page ${pageCount}: ${items.length} produits`);
    all.push(...items);

    // 1) Bouton "Charger plus"
    const hasLoadMore = await page
      .locator(PAGINATION.loadMoreBtn)
      .first()
      .isVisible()
      .catch(() => false);
    if (hasLoadMore) {
      await Promise.all([
        page.click(PAGINATION.loadMoreBtn),
        page.waitForLoadState("domcontentloaded"),
      ]);
      continue; // même page, plus d’items
    }

    // 2) Bouton "suivant"
    const hasNext = await page
      .locator(PAGINATION.nextBtn)
      .first()
      .isVisible()
      .catch(() => false);
    if (hasNext) {
      await Promise.all([
        page.click(PAGINATION.nextBtn),
        page.waitForLoadState("domcontentloaded"),
      ]);
      continue;
    }

    break; // pas de pagination
  }

  // Téléchargement des images
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
          } catch (e) {
            console.warn("⚠️  image download failed:", p.image);
          }
        }
        return { ...p, image_path };
      })
    )
  );

  // Écrit JSON + CSV
  await fs.writeJson(OUT_JSON, withLocalImages, { spaces: 2 });
  console.log(`💾  JSON → ${OUT_JSON}`);

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
