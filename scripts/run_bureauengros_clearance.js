import fs from 'fs';
import path from 'path';
import { chromium } from 'playwright';

const BASE_URL =
  'https://www.bureauengros.com/collections/fr-centre-de-liquidation-7922?configure%5Bfilters%5D=tags%3A%22fr_CA%22&configure%5BruleContexts%5D%5B0%5D=logged-out&refinementList%5Bnamed_tags.clearance_sku%5D%5B0%5D=1&sortBy=shopify_products&page=';

const OUTPUT_DIR = path.join('outputs', 'bureauengros');
const JSON_OUTPUT = path.join(OUTPUT_DIR, 'clearance.json');
const CSV_OUTPUT = path.join(OUTPUT_DIR, 'clearance.csv');
const MAX_PAGES = 120;

const PRICE_PATTERN = /[^0-9,.\-]+/g;

function parsePrice(raw) {
  if (!raw) return null;
  const normalized = String(raw).replace(PRICE_PATTERN, '').replace(',', '.');
  const value = parseFloat(normalized);
  return Number.isFinite(value) ? value : null;
}

function computeDiscountPercent(originalPrice, salePrice) {
  if (!originalPrice || !salePrice || originalPrice <= 0) return null;
  const percent = ((originalPrice - salePrice) / originalPrice) * 100;
  return Math.round(percent);
}

async function extractProducts(page) {
  await page.waitForSelector('div.product-tile.js-product-tile', { timeout: 30000 });
  const tiles = await page.$$('div.product-tile.js-product-tile');

  const products = [];

  for (const tile of tiles) {
    const [title, productUrl, imageUrl, originalPriceText, salePriceText, sku] = await Promise.all([
      tile.$eval('.product-tile__title', (el) => el.innerText.trim()).catch(() => ''),
      tile.$eval('a.product-tile_image-link.productlink', (el) => el.href).catch(() => ''),
      tile.$eval('img.product-tile__image', (el) => el.src || el.getAttribute('data-src') || '').catch(() => ''),
      tile
        .$eval('.product-tile__price-regular, .product-tile__price--compare, .price__regular .money', (el) =>
          el.innerText.trim(),
        )
        .catch(() => ''),
      tile
        .$eval('.product-tile__price-current, .product-tile__price .money, .product-tile__price', (el) =>
          el.innerText.trim(),
        )
        .catch(() => ''),
      tile.getAttribute('data-product-sku'),
    ]);

    const originalPrice = parsePrice(originalPriceText);
    const salePrice = parsePrice(salePriceText);
    const discountPercent = computeDiscountPercent(originalPrice, salePrice);

    if (!title || !productUrl || !salePrice || !originalPrice) continue;
    if (!Number.isFinite(discountPercent) || discountPercent < 50) continue;

    products.push({
      retailer: 'Bureau en Gros',
      sku: sku || '',
      title,
      imageUrl,
      productUrl,
      originalPrice,
      salePrice,
      discountPercent,
    });
  }

  return products;
}

function toCsvRow(values) {
  return values
    .map((value) => {
      if (value === null || value === undefined) return '';
      const text = String(value).replace(/"/g, '""');
      if (text.includes(',') || text.includes('"') || text.includes('\n')) {
        return `"${text}"`;
      }
      return text;
    })
    .join(',');
}

async function scrapeAll() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = [];

  try {
    for (let pageNumber = 1; pageNumber <= MAX_PAGES; pageNumber += 1) {
      const url = `${BASE_URL}${pageNumber}`;
      console.log(`➡️  Visiting page ${pageNumber}: ${url}`);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });

      let pageProducts = [];
      try {
        pageProducts = await extractProducts(page);
      } catch (error) {
        console.warn(`⚠️  Skipping page ${pageNumber} due to error:`, error.message || error);
      }

      if (!pageProducts.length) {
        console.log(`🚪 No products found on page ${pageNumber}. Stopping.`);
        break;
      }

      console.log(`   ↳ Collected ${pageProducts.length} discounted products`);
      results.push(...pageProducts);
    }
  } finally {
    await browser.close();
  }

  return results;
}

async function saveOutputs(products) {
  await fs.promises.mkdir(OUTPUT_DIR, { recursive: true });
  await fs.promises.writeFile(JSON_OUTPUT, JSON.stringify(products, null, 2), 'utf-8');
  console.log(`✅ Saved JSON to ${JSON_OUTPUT}`);

  const headers = ['retailer', 'sku', 'title', 'imageUrl', 'productUrl', 'originalPrice', 'salePrice', 'discountPercent'];
  const csvLines = [headers.join(',')];
  for (const product of products) {
    csvLines.push(
      toCsvRow([
        product.retailer,
        product.sku,
        product.title,
        product.imageUrl,
        product.productUrl,
        product.originalPrice,
        product.salePrice,
        product.discountPercent,
      ]),
    );
  }
  await fs.promises.writeFile(CSV_OUTPUT, csvLines.join('\n'), 'utf-8');
  console.log(`✅ Saved CSV to ${CSV_OUTPUT}`);
}

(async () => {
  try {
    const products = await scrapeAll();
    console.log(`📦 Total qualifying clearance products: ${products.length}`);
    await saveOutputs(products);
  } catch (error) {
    console.error('❌ Scrape failed', error);
    process.exit(1);
  }
})();
