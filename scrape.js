#!/usr/bin/env node
// @ts-check
/**
 * Scraper Canadian Tire - Liquidation (Playwright)
 */
import { chromium } from "playwright";
import fs from "fs-extra";
import path from "path";
import axios from "axios";
import cheerio from "cheerio";
import pLimit from "p-limit";
import sanitize from "sanitize-filename";
import { createObjectCsvWriter } from "csv-writer";
import minimist from "minimist";
import { fileURLToPath } from "url";

const args = minimist(process.argv.slice(2));

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

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ------------- CLI -------------
const START_URL =
  args.url ||
  "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271";
const MAX_PAGES = Number(args.maxPages || 125);
const HEADLESS = !args.headful;
const INCLUDE_REGULAR_PRICE = parseBooleanArg(
  args["include-regular-price"] ?? args.includeRegularPrice,
  true
);
const INCLUDE_LIQUIDATION_PRICE = parseBooleanArg(
  args["include-liquidation-price"] ?? args.includeLiquidationPrice,
  true
);

// ------------- CONFIG -------------
const OUT_DIR = "./images";
const OUT_JSON = "./data.json";
const OUT_CSV = "./data.csv";
const CONCURRENCY = 6;
const DETAIL_CONCURRENCY = 4;

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
  priceSale: [
    "[data-testid='sale-price']",
    "[data-testid='product-price']",
    ".price__value, .sale-price__value, .product-price",
    ".price, .c-pricing__sale, .c-pricing__current",
  ].join(", "),
  priceRegular: [
    "[data-testid='reg-price']",
    "[data-testid='regular-price']",
    "[data-testid='list-price']",
    "[data-testid='was-price']",
    ".price__was, .was-price__value, .product-was-price",
    ".c-pricing__was, .price--was, .price__value--was",
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

function extractQuantityValue(text) {
  if (!text) return null;
  const normalized = text.replace(/\s+/g, "");
  const match = normalized.match(/(\d+)/);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function normalizeText(text) {
  return text ? text.replace(/\s+/g, " ").trim() : "";
}

function firstNonEmptyText($, selectors) {
  for (const selector of selectors) {
    if (!selector) continue;
    const value = normalizeText($(selector).first().text());
    if (value) return value;
  }
  return null;
}

function findSku($) {
  const attributeSources = [
    ["[data-product-sku]", "data-product-sku"],
    ["[data-sku]", "data-sku"],
    ["meta[itemprop='sku']", "content"],
    ["meta[name='sku']", "content"],
    ["meta[property='product:retailer_item_id']", "content"],
  ];
  for (const [selector, attr] of attributeSources) {
    const value = normalizeText($(selector).first().attr(attr));
    if (value) return value;
  }

  let labelValue = null;
  $("body *").each((_, el) => {
    if (labelValue) return false;
    const text = normalizeText($(el).text());
    if (!text) return;

    const directMatch = text.match(/Num[eé]ro d['’]article\s*[:#\-\s]*([A-Za-z0-9-]+)/i);
    if (directMatch && directMatch[1]) {
      labelValue = directMatch[1].trim();
      return false;
    }

    if (/Num[eé]ro d['’]article/i.test(text)) {
      const siblingText = $(el)
        .nextAll()
        .map((_, sib) => normalizeText($(sib).text()))
        .get()
        .find((t) => t);
      if (siblingText) {
        labelValue = siblingText;
        return false;
      }
      const parent = $(el).parent();
      if (parent && parent.length) {
        const siblings = parent.children().toArray();
        const startIdx = siblings.indexOf(el);
        for (let i = (startIdx === -1 ? 0 : startIdx + 1); i < siblings.length; i++) {
          const siblingTextAlt = normalizeText($(siblings[i]).text());
          if (siblingTextAlt) {
            labelValue = siblingTextAlt;
            return false;
          }
        }
      }
    }
  });

  return labelValue;
}

function findAvailability($) {
  const direct = firstNonEmptyText($, [
    "[data-testid='availability']",
    ".availability",
    ".availability-message",
    ".store-availability",
    "[data-store-availability]",
  ]);
  if (direct) return direct;

  let labelValue = null;
  $("body *").each((_, el) => {
    if (labelValue) return false;
    const text = normalizeText($(el).text());
    if (!text) return;
    if (/(en stock|en magasin)/i.test(text)) {
      labelValue = text;
      return false;
    }
  });
  return labelValue;
}

async function fetchProductDetails(url) {
  if (!url) return {};
  try {
    const res = await axios.get(url, {
      timeout: 60000,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        Accept:
          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
      },
    });
    const $ = cheerio.load(res.data);

    const priceSaleRaw = firstNonEmptyText($, [
      ".product-price__sale",
      ".product-price__value--sale",
      ".price--sale",
      ".price__sale",
      ".sale-price",
    ]);

    const priceRegularRaw = firstNonEmptyText($, [
      ".product-price__regular",
      ".product-price__value--regular",
      ".price--regular",
      ".price__was",
      ".was-price",
    ]);

    const priceTextRaw = firstNonEmptyText($, [
      ".product-price",
      ".product__price",
      ".pricing",
      "[data-testid='product-price']",
    ]);

    const sku = findSku($);
    const availabilityRaw = findAvailability($);
    const quantityValue = extractQuantityValue(availabilityRaw);

    return {
      price_sale_raw: priceSaleRaw || null,
      price_regular_raw: priceRegularRaw || null,
      price_text_raw: priceTextRaw || null,
      sku: sku || null,
      quantity_raw: availabilityRaw || null,
      quantity_value: quantityValue,
    };
  } catch (error) {
    const message = error?.response?.status
      ? `${error.response.status}`
      : error?.message || String(error);
    console.warn("⚠️  detail fetch failed:", url, message);
    return {};
  }
}

async function enrichItemsWithDetails(items) {
  if (!items.length) return items;
  const limit = pLimit(DETAIL_CONCURRENCY);
  return Promise.all(
    items.map((item) =>
      limit(async () => {
        if (!item.url) return item;
        const details = await fetchProductDetails(item.url);
        const merged = { ...item };
        if (details.price_sale_raw) merged.price_sale_raw = details.price_sale_raw;
        if (details.price_regular_raw)
          merged.price_regular_raw = details.price_regular_raw;
        if (details.price_text_raw && !merged.price_text_raw)
          merged.price_text_raw = details.price_text_raw;
        if (details.sku) merged.sku = details.sku;
        if (details.quantity_raw) merged.quantity_raw = details.quantity_raw;
        if (details.quantity_value != null)
          merged.quantity_value = details.quantity_value;
        return merged;
      })
    )
  );
}

function normalizeRecord(item) {
  const liquidationPrice = extractPrice(item.price_sale_raw);
  const regularPrice = extractPrice(item.price_regular_raw);
  const fallbackPrice = extractPrice(item.price_text_raw);
  const priceRaw =
    item.price_text_raw || item.price_sale_raw || item.price_regular_raw || null;
  const price = liquidationPrice ?? regularPrice ?? fallbackPrice;

  const record = {
    title: item.title,
    price,
    price_raw: priceRaw,
    liquidation:
      item.liquidation ||
      (liquidationPrice != null &&
        (regularPrice == null || liquidationPrice <= regularPrice)),
    image: item.image,
    url: item.url,
  };

  if (INCLUDE_LIQUIDATION_PRICE) {
    record.liquidation_price = liquidationPrice;
    record.liquidation_price_raw = item.price_sale_raw || null;
  }

  if (INCLUDE_REGULAR_PRICE) {
    record.regular_price = regularPrice;
    record.regular_price_raw = item.price_regular_raw || null;
  }

  if (liquidationPrice != null) {
    record.sale_price = liquidationPrice;
  }

  if (item.price_sale_raw) {
    record.sale_price_raw = item.price_sale_raw;
  }

  if (item.price_text_raw) {
    record.price_text_raw = item.price_text_raw;
  }

  if (item.sku) {
    record.sku = item.sku;
  }

  if (item.quantity_raw) {
    record.quantity = item.quantity_raw;
  }

  const quantityValue =
    item.quantity_value != null
      ? item.quantity_value
      : extractQuantityValue(item.quantity_raw);
  if (quantityValue != null) {
    record.quantity_value = quantityValue;
  }

  return record;
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
      const hasBadge = !!el.querySelector(SELECTORS.badge);
      const text = el.textContent || "";
      const liquidation =
        hasBadge ||
        /liquidation|clearance|soldes?/i.test(title) ||
        /liquidation|clearance|soldes?/i.test(text.slice(0, 400));
      const image = pickImg(el, SELECTORS.image);
      const url = pickHref(el, SELECTORS.link);

      const priceText = pickText(el, ".price");
      const salePriceText = pickText(el, ".sale-price");

      let priceSaleRaw = salePriceText || pickText(el, SELECTORS.priceSale);
      let priceRegularRaw = pickText(el, SELECTORS.priceRegular);

      if (!priceSaleRaw && priceText && salePriceText) {
        priceSaleRaw = salePriceText;
      }

      if (!priceRegularRaw && priceText && !salePriceText) {
        priceRegularRaw = priceText;
      }

      const skuAttr = el.getAttribute("data-sku");
      const skuText = (skuAttr && skuAttr.trim()) || pickText(el, ".sku");
      const quantityText = pickText(el, ".stock");

      return {
        title,
        price_sale_raw: priceSaleRaw || null,
        price_regular_raw: priceRegularRaw || null,
        price_text_raw: priceText || null,
        liquidation,
        image,
        url,
        sku: skuText || null,
        quantity_raw: quantityText || null,
      };
    });
  }, SELECTORS);
  return items;
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
  console.log(
    `⚙️  Options → liquidation_price=${INCLUDE_LIQUIDATION_PRICE ? "on" : "off"}, regular_price=${INCLUDE_REGULAR_PRICE ? "on" : "off"}`
  );

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

  const enriched = await enrichItemsWithDetails(all);
  const normalized = enriched
    .map((item) => normalizeRecord(item))
    .filter((p) => p.title || p.price != null || p.image);

  console.log(`📦  Produits valides: ${normalized.length}`);

  const limit = pLimit(CONCURRENCY);
  let idx = 0;
  const withLocalImages = await Promise.all(
    normalized.map((p) =>
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

  await fs.writeJson(OUT_JSON, withLocalImages, { spaces: 2 });
  console.log(`💾  JSON → ${OUT_JSON}`);

  const csv = createObjectCsvWriter({
    path: OUT_CSV,
    header: [
      { id: "title", title: "title" },
      { id: "price", title: "price" },
      { id: "price_raw", title: "price_raw" },
      ...(INCLUDE_REGULAR_PRICE
        ? [
            { id: "regular_price", title: "regular_price" },
            { id: "regular_price_raw", title: "regular_price_raw" },
          ]
        : []),
      ...(INCLUDE_LIQUIDATION_PRICE
        ? [
            { id: "liquidation_price", title: "liquidation_price" },
            { id: "liquidation_price_raw", title: "liquidation_price_raw" },
          ]
        : []),
      { id: "liquidation", title: "liquidation" },
      { id: "url", title: "url" },
      { id: "image", title: "image" },
      { id: "image_path", title: "image_path" },
      { id: "sale_price", title: "sale_price" },
      { id: "sale_price_raw", title: "sale_price_raw" },
      { id: "price_text_raw", title: "price_text_raw" },
      { id: "sku", title: "sku" },
      { id: "quantity", title: "quantity" },
      { id: "quantity_value", title: "quantity_value" },
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
