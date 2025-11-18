#!/usr/bin/env node
// @ts-check
/**
 * Scraper Canadian Tire - Liquidation (Playwright + enrichissement fiche produit)
 * - Multi-magasins via --store <ID> --city "<Nom>"
 * - Titres/prix robustes (aria-label/title/alt, data-*), scroll "lazy"
 * - Enrichissement depuis la liste uniquement (pas de PDP)
 * - Sorties par magasin: outputs/canadiantire/<store>-<city-slug>/{data.json,data.csv}
 */
import { chromium } from "playwright";
import fs from "fs-extra";
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

const parsedMaxPages = Number(args.maxPages);
const hasExplicitMaxPages = Number.isFinite(parsedMaxPages);
const HARD_MAX_PAGES = 125;
const MAX_PAGES = hasExplicitMaxPages && parsedMaxPages > 0
  ? Math.min(parsedMaxPages, HARD_MAX_PAGES)
  : HARD_MAX_PAGES;
const HEADLESS  = !args.headful;

const INCLUDE_REGULAR_PRICE    = parseBooleanArg(args["include-regular-price"] ?? args.includeRegularPrice, true);
const INCLUDE_LIQUIDATION_PRICE= parseBooleanArg(args["include-liquidation-price"] ?? args.includeLiquidationPrice, true);

// ---------- SORTIES ----------
const citySlug = CITY ? `-${slugify(CITY, { lower:true, strict:true })}` : "";
const OUT_BASE = `./outputs/canadiantire/${STORE_ID || "default"}${citySlug}`;
const OUT_JSON = `${OUT_BASE}/data.json`;
const OUT_CSV  = `${OUT_BASE}/data.csv`;

// (utile pour le workflow si on veut parser les logs)
console.log(`OUT_BASE=${OUT_BASE}`);

// === Helpers & Sélecteurs ===
const BASE = "https://www.canadiantire.ca";

const SELECTORS = {
  card: "li[data-testid='product-grids']",
};

const PAGINATION_NAV_SELECTOR = [
  "nav[aria-label*='pagination' i]",
  "nav[aria-label*='Pagination' i]",
  "[data-testid='pagination']",
  "[data-testid='pagination-container']",
  "nav[role='navigation']:has([aria-current])",
].join(", ");

const SEL = {
  card: "li[data-testid=\"product-grids\"]",
  price: "span[data-testid=\"priceTotal\"], .nl-price--total, .price, .c-pricing__current",
  paginationNav: PAGINATION_NAV_SELECTOR,
  currentPage: `${PAGINATION_NAV_SELECTOR} [aria-current], ${PAGINATION_NAV_SELECTOR} [aria-current=\"page\"]`,
};

const cleanMoney = (s) => {
  if (!s) return null;
  s = s.replace(/\u00a0/g, " ").trim();
  const m = s.match(/(\d[\d\s.,]*)(?:\s*\$)?/);
  return m ? m[1].replace(/\s/g, "") : s;
};

async function dismissMedalliaPopup(page) {
  try {
    const possibleCloseButtons = page.locator(
      [
        '#kampyleInviteContainer button',
        '#MDigitalInvitationWrapper button',
        'button[aria-label*="close" i]',
        'button[aria-label*="fermer" i]',
        'button[aria-label*="feedback" i]'
      ].join(', ')
    );

    const count = await possibleCloseButtons.count();
    for (let i = 0; i < count; i++) {
      const btn = possibleCloseButtons.nth(i);
      if (await btn.isVisible().catch(() => false)) {
        console.log('🧹 Medallia: clic sur le bouton de fermeture');
        await btn.click({ timeout: 2000 }).catch(() => {});
        break;
      }
    }

    await page.evaluate(() => {
      const ids = ['MDigitalInvitationWrapper', 'kampyleInviteContainer', 'kampyleInvite'];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el) {
          console.log('🧹 Medallia: suppression/masquage de', id);
          el.remove();
        }
      }

      ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('pointer-events', 'none', 'important');
        }
      });
    });
  } catch (e) {
    console.warn('⚠️ Impossible de fermer le pop-up Medallia:', e);
  }
}

async function waitProductsStable(page, timeout = 30000) {
  const start = Date.now();
  await page.waitForSelector(SEL.card, { timeout });

  const priceTimeout = Math.min(2500, Math.max(900, Math.floor(timeout / 5)));
  await Promise.race([
    page.waitForSelector(SEL.price, { timeout: priceTimeout }),
    page.waitForTimeout(priceTimeout + 120),
  ]).catch(() => {});

  const elapsed = Date.now() - start;
  const remaining = Math.max(900, timeout - elapsed);
  try {
    await page.waitForFunction(
      () => document.querySelectorAll('li[data-testid="product-grids"]').length > 0,
      { timeout: remaining }
    );
  } catch (err) {
    const count = await page.locator(SEL.card).count().catch(() => 0);
    if (count === 0) throw err;
  }
}

async function getTotalPages(page) {
  const nav = page.locator(SEL.paginationNav).first();
  if (!(await nav.count())) return 1;

  const links = nav.locator("a, button");
  const n = await links.count();
  let max = 1;
  for (let i = 0; i < n; i++) {
    const btn = links.nth(i);
    const disabled = await btn.getAttribute("aria-disabled");
    if (disabled === "true") continue;
    const label = (await btn.getAttribute("aria-label")) || (await btn.textContent()) || "";
    const m = label.match(/(\d+)/);
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }

  if (max === 1) {
    const navText = ((await nav.textContent().catch(() => "")) || "").trim();
    const match = navText.match(/(?:sur|of)\s*(\d+)/i);
    if (match) {
      const parsed = parseInt(match[1], 10);
      if (Number.isFinite(parsed)) max = parsed;
    }
  }

  return max;
}

async function getCurrentPageNum(page) {
  try {
    const el = page.locator(SEL.currentPage);
    const label = (await el.getAttribute("aria-label")) || (await el.textContent()) || "";
    const m = label.match(/(\d+)/);
    return m ? parseInt(m[1], 10) : 1;
  } catch {
    return 1;
  }
}

async function findPaginationTarget(page, nextPage) {
  const nav = page.locator(SEL.paginationNav).first();
  if (!(await nav.count())) return null;

  const items = nav.locator("a, button");
  const hiddenCandidates = [];
  const count = await items.count();
  const numberPattern = new RegExp(`\\b${nextPage}\\b`);
  for (let i = 0; i < count; i++) {
    const item = items.nth(i);
    const disabled = await item.getAttribute("aria-disabled");
    if (disabled === "true") continue;
    const label = ((await item.getAttribute("aria-label")) || (await item.textContent()) || "").trim();
    if (!label) continue;
    if (numberPattern.test(label)) {
      if (await item.isVisible().catch(() => false)) return item;
      hiddenCandidates.push(item);
    }
  }

  const arrowSelectors = [
    "button[aria-label*='Suiv']",
    "a[aria-label*='Suiv']",
    "button[aria-label*='Next']",
    "a[aria-label*='Next']",
    "button[rel='next']",
    "a[rel='next']",
  ];
  for (const selector of arrowSelectors) {
    const loc = nav.locator(selector).first();
    if (await loc.count()) {
      const disabled = await loc.getAttribute("aria-disabled");
      if (disabled === "true") continue;
      if (await loc.isVisible().catch(() => false)) return loc;
      hiddenCandidates.push(loc);
    }
  }

  if (hiddenCandidates.length) return hiddenCandidates[0];

  const textFallbacks = [
    nav.locator("button:has-text('Suivant')"),
    nav.locator("a:has-text('Suivant')"),
    nav.locator("button:has-text('Next')"),
    nav.locator("a:has-text('Next')"),
  ];
  for (const loc of textFallbacks) {
    if (await loc.count()) {
      if (await loc.first().isVisible().catch(() => false)) return loc.first();
      hiddenCandidates.push(loc.first());
    }
  }

  return hiddenCandidates.length ? hiddenCandidates[0] : null;
}

async function extractFromCard(card) {
  const data = await card.evaluate((el, { base }) => {
    const cleanMoney = (s) => {
      if (!s) return null;
      s = s.replace(/\u00a0/g, " ").trim();
      const m = s.match(/(\d[\d\s.,]*)(?:\s*\$)?/);
      return m ? m[1].replace(/\s/g, "") : s;
    };

    const textFromEl = (node) => {
      if (!node) return null;
      const t = node.textContent;
      return t ? t.trim() : null;
    };

    const titleEl = el.querySelector("[id^='title__promolisting-'], .nl-product-card__title");
    const title = textFromEl(titleEl);

    const imgEl = el.querySelector(".nl-product-card__image-wrap img");
    let image = null;
    if (imgEl) image = imgEl.getAttribute("src") || imgEl.getAttribute("data-src");
    if (image && image.startsWith("//")) image = `https:${image}`;
    if (image && image.startsWith("/")) image = base + image;

    const availability = textFromEl(el.querySelector(".nl-product-card__availability-message"));

    const badges = Array.from(el.querySelectorAll(".nl-plp-badges"))
      .map((node) => textFromEl(node))
      .filter(Boolean);

    let link = null;
    const titleAnchor = titleEl ? titleEl.closest("a") : null;
    if (titleAnchor) link = titleAnchor.getAttribute("href");
    if (!link) {
      const any = el.querySelector("a[href*='/p/'], a[href*='/product/']");
      if (any) link = any.getAttribute("href");
    }
    if (link && link.startsWith("/")) link = base + link;

    const productId = el.getAttribute("data-product-id") || el.getAttribute("data-productid") || null;

    return {
      name: title || null,
      image: image || null,
      availability: availability || null,
      badges,
      link: link || null,
      product_id: productId,
    };
  }, { base: BASE });

  return data;
}

async function scrapeListing(page, { skipGuards = false } = {}) {
  if (!skipGuards) {
    await page.waitForSelector(SELECTORS.card, { timeout: 45000 });
    await page.waitForSelector("span[data-testid='priceTotal'], .nl-price--total", { timeout: 20000 }).catch(() => {});
  } else {
    const hasCards = await page.locator(SELECTORS.card).count();
    if (!hasCards) {
      await page.waitForSelector(SELECTORS.card, { timeout: 20000 });
    }
  }

  const cardsLocator = page.locator(SELECTORS.card);
  try {
    const items =
      (await cardsLocator.evaluateAll((nodes, { base }) => {
      const cleanMoney = (s) => {
        if (!s) return null;
        s = s.replace(/\u00a0/g, " ").trim();
        const m = s.match(/(\d[\d\s.,]*)(?:\s*\$)?/);
        return m ? m[1].replace(/\s/g, "") : s;
      };

      const textFromEl = (node) => {
        if (!node) return null;
        const t = node.textContent;
        return t ? t.trim() : null;
      };

      return nodes.map((el) => {
        const titleEl = el.querySelector("[id^='title__promolisting-'], .nl-product-card__title");
        const title = textFromEl(titleEl);

        const priceSaleRaw = textFromEl(el.querySelector("span[data-testid='priceTotal'], .nl-price--total"));
        const priceWasRaw = textFromEl(el.querySelector(".nl-price__was s, .nl-price__was, .nl-price--was, .nl-price__change s"));
        const price_sale = cleanMoney(priceSaleRaw);
        const price_original = cleanMoney(priceWasRaw);

        const imgEl = el.querySelector(".nl-product-card__image-wrap img");
        let image = null;
        if (imgEl) image = imgEl.getAttribute("src") || imgEl.getAttribute("data-src");
        if (image && image.startsWith("//")) image = `https:${image}`;
        if (image && image.startsWith("/")) image = base + image;

        const availability = textFromEl(el.querySelector(".nl-product-card__availability-message"));

        const badges = Array.from(el.querySelectorAll(".nl-plp-badges"))
          .map((node) => textFromEl(node))
          .filter(Boolean);

        let link = null;
        const titleAnchor = titleEl ? titleEl.closest("a") : null;
        if (titleAnchor) link = titleAnchor.getAttribute("href");
        if (!link) {
          const any = el.querySelector("a[href*='/p/'], a[href*='/product/']");
          if (any) link = any.getAttribute("href");
        }
        if (link && link.startsWith("/")) link = base + link;

        const productId = el.getAttribute("data-product-id") || el.getAttribute("data-productid") || null;

        return {
          name: title || null,
          price_sale,
          price_sale_raw: priceSaleRaw || null,
          price_original,
          price_original_raw: priceWasRaw || null,
          image: image || null,
          availability: availability || null,
          badges,
          link: link || null,
          product_id: productId,
        };
      });
    }, { base: BASE })) || [];

    return items;
  } catch (e) {
    console.warn("scrapeListing evaluateAll error:", e?.message || e);
    if (!skipGuards) {
      await page.waitForSelector(SELECTORS.card, { timeout: 20000 }).catch(() => {});
    }
    const cards = page.locator(SELECTORS.card);
    const n = await cards.count();
    const tasks = [];
    for (let i = 0; i < n; i++) {
      const card = cards.nth(i);
      tasks.push(
        extractFromCard(card).catch((err) => {
          console.warn("extractFromCard error:", err?.message || err);
          return null;
        })
      );
    }
    const out = await Promise.all(tasks);
    return out.filter(Boolean);
  }
}

// ---------- UTILS ----------
function extractPrice(text) {
  if (text == null) return null;
  const normalized = String(text);
  const m = normalized.replace(/\s/g, "").match(/(\d+[\.,]?\d*)/);
  return m ? parseFloat(m[1].replace(",", ".")) : null;
}

function computeDiscountPercent(regularPrice, liquidationPrice) {
  if (regularPrice == null || liquidationPrice == null) return null;
  if (regularPrice <= 0 || liquidationPrice <= 0) return null;

  const discount = ((regularPrice - liquidationPrice) / regularPrice) * 100;
  return Number.isFinite(discount) ? discount : null;
}

function createRecordFromCard(card, pageIsClearance) {
  const priceSaleRaw = card.price_sale_raw ?? card.price_sale ?? null;
  const priceWasRaw = card.price_original_raw ?? card.price_original ?? null;
  const salePrice = extractPrice(priceSaleRaw ?? undefined);
  const regularPrice = extractPrice(priceWasRaw ?? undefined);
  const priceRaw = priceSaleRaw || priceWasRaw || null;
  const price = salePrice ?? regularPrice ?? null;

  const discountPercent =
    card.discount_percent != null
      ? card.discount_percent
      : computeDiscountPercent(regularPrice, salePrice);

  const meetsDiscountThreshold =
    regularPrice != null &&
    salePrice != null &&
    regularPrice > 0 &&
    salePrice > 0 &&
    discountPercent >= 50;

  if (!meetsDiscountThreshold) return null;

  const discount_percent =
    discountPercent != null ? Math.round(discountPercent * 100) / 100 : null;

  const badges = Array.isArray(card.badges) ? card.badges : [];
  const normalizedBadges = badges.map((b) => b.toLowerCase());
  const hasLiquidationBadge = normalizedBadges.some((b) => /liquidation|clearance/.test(b));
  const isLiquidation = hasLiquidationBadge ||
    (pageIsClearance && salePrice != null && (regularPrice == null || salePrice <= regularPrice));

  const rec = {
    store_id: STORE_ID || null,
    city: CITY || null,
    name: card.name || null,
    title: card.name || null,
    price,
    price_raw: priceRaw,
    liquidation: !!isLiquidation,
    image: card.image || null,
    image_url: card.image || null,
    url: card.link || null,
    link: card.link || null,
    product_id: card.product_id || null,
    availability: card.availability || null,
    badges,
    discount_percent,
  };

  if (INCLUDE_LIQUIDATION_PRICE) {
    rec.liquidation_price = salePrice ?? null;
    rec.liquidation_price_raw = priceSaleRaw || null;
    rec.sale_price = salePrice ?? null;
    rec.sale_price_raw = priceSaleRaw || null;
  }
  if (INCLUDE_REGULAR_PRICE) {
    rec.regular_price = regularPrice ?? null;
    rec.regular_price_raw = priceWasRaw || null;
  }

  rec.price_sale_clean = card.price_sale || null;
  rec.price_original_clean = card.price_original || null;

  return rec;
}

async function lazyWarmup(page) {
  // scroll rapide pour déclencher lazy render des prix/images sans multiplier les pauses
  await page.evaluate(async () => {
    const viewport = window.innerHeight || 800;
    const maxScroll = document.body.scrollHeight || viewport;
    if (maxScroll <= viewport * 1.15) {
      window.scrollTo(0, 0);
      return;
    }
    const step = Math.max(260, Math.floor(viewport * 1.3));
    const delay = 35;
    for (let y = 0; y < maxScroll; y += step) {
      window.scrollTo(0, y);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(40);
  await Promise.race([
    page.waitForSelector(
      "[data-testid='sale-price'], [data-testid='regular-price'], span[data-testid='priceTotal'], .nl-price--total, .price, .price__value",
      { timeout: 4500 }
    ),
    page.waitForTimeout(650),
  ]).catch(()=>{});
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

  await page.route("**/*medallia*", (route) => route.abort());
  await page.route("**/resources.digital-cloud.medallia.ca/**", (route) => route.abort());

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
  const seenProducts = new Set();

  await waitProductsStable(page);
  await lazyWarmup(page);

  let pagePrimed = true;
  const totalPages = await getTotalPages(page);
  const currentPage = await getCurrentPageNum(page);
  const lastPage = Math.min(totalPages, MAX_PAGES);
  if (totalPages > MAX_PAGES) {
    console.log(`⚠️  Limitation: maximum ${MAX_PAGES} pages seront parcourues sur ${totalPages} disponibles.`);
  }

  for (let p = currentPage; p <= lastPage; p++) {
    const skipGuards = pagePrimed;
    if (!pagePrimed) {
      await waitProductsStable(page);
      await lazyWarmup(page);
    }
    pagePrimed = false;

    const cards = await scrapeListing(page, { skipGuards });
    const pageIsClearance = /\/liquidation\.html/i.test(await page.url());
    const batch = [];
    const pageSeen = new Set();
    for (const card of cards) {
      const regularPriceForCheck = extractPrice(
        card.price_original_raw ??
        card.price_original ??
        card.regular_price ??
        null
      );
      const salePriceForCheck = extractPrice(
        card.price_sale_raw ??
        card.price_sale ??
        card.sale_price ??
        null
      );

      const discountPercent = computeDiscountPercent(
        regularPriceForCheck,
        salePriceForCheck
      );

      if (
        discountPercent == null ||
        discountPercent < 50
      ) {
        continue;
      }

      const normalizedLink = card.link ? card.link.split("?")[0].toLowerCase() : null;
      const linkKey = normalizedLink ? `link:${normalizedLink}` : null;
      const productId = card.product_id ? `id:${card.product_id}` : null;
      const keys = [linkKey, productId].filter(Boolean);
      let duplicate = false;
      if (keys.length) {
        for (const key of keys) {
          if (seenProducts.has(key)) {
            duplicate = true;
            break;
          }
        }
        if (duplicate) continue;
        keys.forEach((key) => seenProducts.add(key));
      } else {
        const fallbackKey = card.name
          ? `${card.name}|${card.price_sale || ""}|${card.price_original || ""}|${card.image || ""}`.toLowerCase()
          : null;
        if (fallbackKey) {
          if (pageSeen.has(fallbackKey)) continue;
          pageSeen.add(fallbackKey);
        }
      }
      const record = createRecordFromCard(
        { ...card, discount_percent: discountPercent },
        pageIsClearance
      );
      if (!record) continue;
      if (record.title || record.price != null || record.image) batch.push(record);
    }
    console.log(`✅ Page ${p}: ${batch.length} produits`);
    all.push(...batch);

    if (((p - currentPage + 1) % 10) === 0) await page.waitForTimeout(550);

    if (p === lastPage) break;

    const target = await findPaginationTarget(page, p + 1);
    if (!target) {
      console.warn(`Lien de pagination introuvable pour la page ${p + 1}, arrêt.`);
      break;
    }

    if (!(await target.isVisible().catch(() => false))) {
      await page.locator(SEL.paginationNav).scrollIntoViewIfNeeded().catch(() => {});
      await page.waitForTimeout(100);
    }

    await target.scrollIntoViewIfNeeded().catch(() => {});

    const clickNavigation = (async () => {
      await dismissMedalliaPopup(page);
      if (await target.isVisible().catch(() => false)) {
        try {
          await target.click({ timeout: 12000 });
        } catch (err) {
          console.warn('⚠️ Pagination click blocked, retrying after dismissing Medallia popup...', err);
          await dismissMedalliaPopup(page);
          await target.click({ timeout: 12000 });
        }
      } else {
        await target.evaluate((el) => { if (el) el.click(); }).catch(() => {});
      }
    })();

    await Promise.all([
      clickNavigation,
      page.waitForFunction(
        (expected) => {
          const el = document.querySelector('nav[aria-label="pagination"] [aria-current="page"]');
          if (!el) return false;
          const txt = el.getAttribute('aria-label') || el.textContent || '';
          return new RegExp(`\\b${expected}\\b`).test(txt);
        },
        p + 1,
        { timeout: 30000 }
      ).catch(() => {}),
    ]);

    await Promise.race([
      page.waitForLoadState("networkidle").catch(() => {}),
      page.waitForTimeout(1200),
    ]);

    await waitProductsStable(page);
    await lazyWarmup(page);
    await page.waitForTimeout(150);
    pagePrimed = true;
  }

  const results = all.map((out) => ({ ...out, image_url: out.image_url ?? out.image ?? null }));

  await fs.writeJson(OUT_JSON, results, { spaces: 2 });
  console.log(`💾  JSON → ${OUT_JSON}`);

  const csv = createObjectCsvWriter({
    path: OUT_CSV,
    header: [
      { id: "store_id", title: "store_id" },
      { id: "city", title: "city" },
      { id: "name", title: "name" },
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
      { id: "link", title: "link" },
      { id: "image", title: "image" },
      { id: "image_url", title: "image_url" },
      { id: "product_id", title: "product_id" },
      { id: "availability", title: "availability" },
      { id: "badges", title: "badges" },
      { id: "discount_percent", title: "discount_percent" },
      { id: "price_sale_clean", title: "price_sale_clean" },
      { id: "price_original_clean", title: "price_original_clean" },
    ],
  });
  await csv.writeRecords(results);
  console.log(`📄  CSV  → ${OUT_CSV}`);

  await browser.close();
}

main().catch((e) => { console.error("❌ Error:", e); process.exit(1); });
