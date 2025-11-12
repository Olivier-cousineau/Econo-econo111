#!/usr/bin/env node
// @ts-check
/**
 * Scraper Canadian Tire - Liquidation (Playwright + enrichissement fiche produit)
 * - Multi-magasins via --store <ID> --city "<Nom>"
 * - Titres/prix robustes (aria-label/title/alt, data-*), scroll "lazy"
 * - Enrichissement PDP (titre, prix, sku, quantité)
 * - Sorties par magasin: outputs/canadiantire/<store>-<city-slug>/{data.json,data.csv,images/}
 */
import { chromium } from "playwright";
import fs from "fs-extra";
import path from "path";
import axios from "axios";
import pLimit from "p-limit";
import sanitize from "sanitize-filename";
import slugify from "slugify";
import { createObjectCsvWriter } from "csv-writer";
import minimist from "minimist";

const args = minimist(process.argv.slice(2));

function parseBooleanArg(value, defaultValue = false) {
  if (value === undefined) return defaultValue;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["false","0","no","off"].includes(normalized)) return false;
    if (["true","1","yes","on"].includes(normalized)) return true;
  }
  return defaultValue;
}

// ---------- CLI ----------
const STORE_ID = (args.store && String(args.store)) || null;
const CITY     = args.city ? String(args.city) : null;

const DEFAULT_BASE = "https://www.canadiantire.ca/fr/promotions/liquidation.html";
const START_URL = args.url || (STORE_ID ? `${DEFAULT_BASE}?store=${STORE_ID}` : `${DEFAULT_BASE}?store=271`);

const MAX_PAGES = Number(args.maxPages || 125);
const HEADLESS  = !args.headful;

const INCLUDE_REGULAR_PRICE    = parseBooleanArg(args["include-regular-price"] ?? args.includeRegularPrice, true);
const INCLUDE_LIQUIDATION_PRICE= parseBooleanArg(args["include-liquidation-price"] ?? args.includeLiquidationPrice, true);

// ---------- SORTIES ----------
const citySlug = CITY ? `-${slugify(CITY, { lower:true, strict:true })}` : "";
const OUT_BASE = `./outputs/canadiantire/${STORE_ID || "default"}${citySlug}`;
const OUT_DIR  = `${OUT_BASE}/images`;
const OUT_JSON = `${OUT_BASE}/data.json`;
const OUT_CSV  = `${OUT_BASE}/data.csv`;

// (utile pour le workflow si on veut parser les logs)
console.log(`OUT_BASE=${OUT_BASE}`);

const CONCURRENCY = 5;

// ---------- SELECTORS ----------
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
    ".sale-price, .product__sale-price, .price-current",
  ].join(", "),
  priceRegular: [
    "[data-testid='reg-price']",
    "[data-testid='regular-price']",
    "[data-testid='list-price']",
    "[data-testid='was-price']",
    ".price__was, .was-price__value, .product-was-price",
    ".c-pricing__was, .price--was, .price__value--was",
    ".regular-price, .product__was-price, .price-old",
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
  waitForList: "ul[data-testid='product-grids'], .product-grid",
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

// ---------- UTILS ----------
function extractPrice(text) {
  if (!text) return null;
  const m = text.replace(/\s/g, "").match(/([0-9]+(?:[.,][0-9]{2})?)/);
  if (!m) return null;
  const num = Number(m[1].replace(",", "."));
  return Number.isFinite(num) ? num : null;
}

async function downloadImage(url, idx, title) {
  if (!url) return null;
  await fs.ensureDir(OUT_DIR);
  let ext = ".jpg";
  try {
    const u = new URL(url);
    const guess = path.extname(u.pathname).split("?")[0];
    if (guess) ext = guess || ext;
  } catch {}
  const name = sanitize(`${String(idx).padStart(4,"0")}-${(title || "product").slice(0,40)}`)+ext;
  const outPath = path.join(OUT_DIR, name);
  const res = await axios.get(url, { responseType: "arraybuffer", timeout: 60000 });
  await fs.writeFile(outPath, res.data);
  return outPath;
}

async function lazyWarmup(page) {
  // scroll pour déclencher lazy render des prix/images
  await page.evaluate(() => new Promise(res => {
    let y = 0;
    const step = Math.floor(window.innerHeight * 0.9);
    const t = setInterval(() => {
      window.scrollTo(0, y);
      y += step;
      if (y >= document.body.scrollHeight) { clearInterval(t); res(); }
    }, 120);
  }));
  await page.waitForSelector(
    "[data-testid='sale-price'], [data-testid='regular-price'], .price, .price__value",
    { timeout: 15000 }
  ).catch(()=>{});
}

async function scrapeListOnce(page) {
  const items = await page.$$eval(SELECTORS.product, (cards, SELECTORS) => {
    const nodeText = n => (n ? (n.textContent || "").trim() : "");
    const firstAttr = (el, attrs) => {
      for (const a of attrs) { const v = el?.getAttribute?.(a); if (v) return v.trim(); }
      return null;
    };
    const abs = u => new URL(u, location.href).toString();

    const pickImg = (el, sel) => {
      const n = el.querySelector(sel);
      if (!n) return null;
      const v = firstAttr(n, ["src","data-src","data-original","data-image","srcset","data-lazy"]);
      if (!v) return null;
      if (v.includes("srcset")) return abs(v.split(",")[0].trim().split(" ")[0]);
      return abs(v);
    };
    const pickHref = (el, sel) => {
      const a = el.querySelector(sel);
      return a ? abs(a.getAttribute("href")) : null;
    };

    return cards.map((el) => {
      // ----- title
      let title = "";
      const tNode = el.querySelector(SELECTORS.title) || el.querySelector("a[href]");
      if (tNode) {
        title = tNode.getAttribute("aria-label")
              || tNode.getAttribute("title")
              || tNode.getAttribute("alt")
              || nodeText(tNode);
      }

      // ----- prices
      const saleNode = el.querySelector(SELECTORS.priceSale);
      const regNode  = el.querySelector(SELECTORS.priceRegular);
      const priceTextNode = el.querySelector(".price");

      const saleRaw = saleNode?.getAttribute?.("data-price")
                   || saleNode?.getAttribute?.("data-value")
                   || nodeText(saleNode);
      const regRaw  = regNode?.getAttribute?.("data-price")
                   || regNode?.getAttribute?.("data-value")
                   || nodeText(regNode);
      const priceTextRaw = nodeText(priceTextNode);

      const hasBadge = !!el.querySelector(SELECTORS.badge);
      const image = pickImg(el, SELECTORS.image);
      const url   = pickHref(el, SELECTORS.link);

      // sku/qty éventuels en grille
      const sku = el.getAttribute("data-sku") || nodeText(el.querySelector(".sku")) || null;
      const quantity = nodeText(el.querySelector(".stock")) || null;

      return {
        title, image, url,
        price_sale_raw: saleRaw || null,
        price_regular_raw: regRaw || null,
        price_text_raw: priceTextRaw || null,
        has_clearance_badge: hasBadge,
        sku, quantity
      };
    });
  }, SELECTORS);

  const pageIsClearance = /\/liquidation\.html/i.test(await page.url());

  return items.map((it) => {
    const liquidationPrice = extractPrice(it.price_sale_raw || it.price_text_raw);
    const regularPrice     = extractPrice(it.price_regular_raw);
    const priceRaw = it.price_text_raw || it.price_sale_raw || it.price_regular_raw || null;
    const price = liquidationPrice ?? regularPrice ?? null;

    const isLiquidation = it.has_clearance_badge ||
      (pageIsClearance && liquidationPrice != null &&
       (regularPrice == null || liquidationPrice <= regularPrice));

    const rec = {
      store_id: STORE_ID || null,
      city: CITY || null,
      title: it.title || null,
      price,
      price_raw: priceRaw,
      liquidation: !!isLiquidation,
      image: it.image,
      url: it.url,
      sku: it.sku || null,
      quantity: it.quantity || null
    };

    if (INCLUDE_LIQUIDATION_PRICE) {
      rec.liquidation_price = liquidationPrice ?? null;
      rec.liquidation_price_raw = it.price_sale_raw || null;
      rec.sale_price = liquidationPrice ?? null;
      rec.sale_price_raw = it.price_sale_raw || null;
    }
    if (INCLUDE_REGULAR_PRICE) {
      rec.regular_price = regularPrice ?? null;
      rec.regular_price_raw = it.price_regular_raw || null;
    }
    if (it.price_text_raw) rec.price_text_raw = it.price_text_raw;

    return rec;
  }).filter(p => p.title || p.price != null || p.image);
}

async function enrichWithDetails(context, item) {
  if (!item.url) return item;
  try {
    const pp = await context.newPage();
    await pp.goto(item.url, { timeout: 90000, waitUntil: "domcontentloaded" });
    await pp.waitForTimeout(1200);

    // titre
    const title = (await pp.locator("h1, [data-testid='product-title']").first().textContent().catch(()=>null))?.trim();

    // prix
    const saleTxt = (await pp.locator("[data-testid='sale-price'], .price__value, .c-pricing__current").first().textContent().catch(()=>null))?.trim();
    const regTxt  = (await pp.locator("[data-testid='regular-price'], [data-testid='was-price'], .price__was").first().textContent().catch(()=>null))?.trim();
    const saleNum = extractPrice(saleTxt);
    const regNum  = extractPrice(regTxt);

    // sku / quantité
    const skuTxt = (await pp.locator(".ProductDetails__Sku, .sku, .spec-row:has-text('Sku')").first().textContent().catch(()=>null))?.trim();
    const qtyTxt = (await pp.locator(".storeAvailableStock, .prod-availability, .stock-info").first().textContent().catch(()=>null))?.trim();

    await pp.close();

    const out = { ...item };
    if (!out.title && title) out.title = title;
    if (out.price == null) out.price = saleNum ?? regNum ?? out.price;

    if (out.liquidation_price == null && saleNum != null) out.liquidation_price = saleNum;
    if (out.regular_price == null && regNum != null) out.regular_price = regNum;

    if (!out.sale_price && saleNum != null) out.sale_price = saleNum;
    if (!out.sale_price_raw && saleTxt) out.sale_price_raw = saleTxt;
    if (!out.regular_price_raw && regTxt) out.regular_price_raw = regTxt;

    if (!out.sku && skuTxt) out.sku = skuTxt;
    if (!out.quantity && qtyTxt) out.quantity = qtyTxt;

    return out;
  } catch {
    return item;
  }
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
      const loc = page.locator(sel).first();
      if (await loc.isVisible().catch(()=>false)) {
        await loc.click().catch(()=>{});
        await page.waitForTimeout(500);
      }
    } catch {}
  }
}

async function selectStoreById(page, storeIdFromUrl) {
  try {
    // Ouvre et tente de définir le magasin si un module est visible
    await page.click("button:has-text('Sélectionner le magasin'), button:has-text('Choose Store')", { timeout: 5000 }).catch(()=>{});
    // Clique sur un résultat contenant l'ID (quand présent)
    const card = page.locator(`[data-store-id='${storeIdFromUrl}'], [href*='store=${storeIdFromUrl}']`).first();
    if (await card.isVisible().catch(()=>false)) await card.click().catch(()=>{});
    await page.click("button:has-text('Définir ce magasin'), button:has-text('Set as My Store')", { timeout: 5000 }).catch(()=>{});
    await page.waitForTimeout(800);
  } catch {}
}

// ---------- MAIN ----------
async function main() {
  const browser = await chromium.launch({ headless: HEADLESS, args: ["--disable-dev-shm-usage"] });
  const context = await browser.newContext({ locale: "fr-CA" });
  const page = await context.newPage();

  console.log("➡️  Go to:", START_URL);
  console.log(`⚙️  Options → liquidation_price=${INCLUDE_LIQUIDATION_PRICE ? "on":"off"}, regular_price=${INCLUDE_REGULAR_PRICE ? "on":"off"}`);

  // 1) charger
  let retries = 3;
  while (retries > 0) {
    try { await page.goto(START_URL, { timeout: 120000, waitUntil: "domcontentloaded" }); break; }
    catch (e) { if (--retries === 0) throw e; console.log("Retrying page load..."); await page.waitForTimeout(3000); }
  }

  await maybeCloseStoreModal(page);

  // 2) forcer le magasin si présent dans l'URL puis recharger
  const m = START_URL.match(/[?&]store=(\d+)/);
  const storeIdFromUrl = m ? m[1] : null;
  if (storeIdFromUrl) {
    await selectStoreById(page, storeIdFromUrl);
    await page.goto(START_URL, { timeout: 120000, waitUntil: "domcontentloaded" }).catch(()=>{});
  }

  await fs.ensureDir(OUT_BASE);

  const all = [];
  let pageCount = 0;

  while (pageCount < MAX_PAGES) {
    pageCount += 1;
    try { await page.waitForSelector(PAGINATION.waitForList, { timeout: 15000 }); } catch {}
    await lazyWarmup(page);

    const batch = await scrapeListOnce(page);
    console.log(`✅ Page ${pageCount}: ${batch.length} produits`);
    all.push(...batch);

    if (pageCount % 10 === 0) await page.waitForTimeout(1200);

    const loadMore = page.locator(PAGINATION.loadMoreBtn).first();
    if (await loadMore.isVisible().catch(()=>false)) {
      await Promise.all([ loadMore.click({ delay: 30 }).catch(()=>{}), page.waitForLoadState("domcontentloaded") ]);
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 20000 }).catch(()=>{});
      await page.waitForTimeout(600);
      continue;
    }

    const next = nextBtn(page);
    if (await next.isVisible().catch(()=>false)) {
      const before = page.url();
      await next.click({ delay: 30 }).catch(()=>{});
      await page.waitForLoadState("domcontentloaded");
      await page.waitForSelector(PAGINATION.waitForList, { timeout: 20000 }).catch(()=>{});
      await page.waitForTimeout(600);
      if (page.url() === before) {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await page.waitForTimeout(600);
      }
      continue;
    }
    break;
  }

  // Enrichissement PDP (limite soft)
  const limit = pLimit(CONCURRENCY);
  let idx = 0;
  const enriched = await Promise.all(
    all.map((p, i) => limit(async () => {
      // télécharge image
      idx += 1;
      let image_path = null;
      if (p.image) {
        try { image_path = await downloadImage(p.image, idx, p.title); }
        catch { console.warn("⚠️ image download failed:", p.image); }
      }
      // enrichir ~jusqu'à 60 items/lot pour rester soft
      let out = p;
      if (i < 60) out = await enrichWithDetails(context, p);
      return { ...out, image_path };
    }))
  );

  await fs.writeJson(OUT_JSON, enriched, { spaces: 2 });
  console.log(`💾  JSON → ${OUT_JSON}`);

  const csv = createObjectCsvWriter({
    path: OUT_CSV,
    header: [
      { id: "store_id", title: "store_id" },
      { id: "city", title: "city" },
      { id: "title", title: "title" },
      { id: "price", title: "price" },
      { id: "price_raw", title: "price_raw" },
      ...(INCLUDE_REGULAR_PRICE ? [
        { id: "regular_price", title: "regular_price" },
        { id: "regular_price_raw", title: "regular_price_raw" },
      ] : []),
      ...(INCLUDE_LIQUIDATION_PRICE ? [
        { id: "liquidation_price", title: "liquidation_price" },
        { id: "liquidation_price_raw", title: "liquidation_price_raw" },
        { id: "sale_price", title: "sale_price" },
        { id: "sale_price_raw", title: "sale_price_raw" },
      ] : []),
      { id: "liquidation", title: "liquidation" },
      { id: "url", title: "url" },
      { id: "image", title: "image" },
      { id: "image_path", title: "image_path" },
      { id: "sku", title: "sku" },
      { id: "quantity", title: "quantity" },
    ],
  });
  await csv.writeRecords(enriched);
  console.log(`📄  CSV  → ${OUT_CSV}`);

  await browser.close();
}

main().catch((e) => { console.error("❌ Error:", e); process.exit(1); });
