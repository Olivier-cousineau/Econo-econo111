import fs from 'fs';
import path from 'path';
import { chromium } from 'playwright';

const BASE_URL = 'https://www.bureauengros.com/collections/fr-centre-de-liquidation-7922?configure%5Bfilters%5D=tags%3A%22fr_CA%22&configure%5BruleContexts%5D%5B0%5D=logged-out&refinementList%5Bnamed_tags.clearance_sku%5D%5B0%5D=1&sortBy=shopify_products&page=';
const OUTPUT_DIR = path.join('outputs', 'bureauengros', 'clearance');
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'data.json');
const MAX_PAGES = 80;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parsePrice(raw) {
  if (!raw) return null;
  const normalized = String(raw)
    .replace(/[^0-9,\.\-]+/g, '')
    .replace(',', '.');
  const value = parseFloat(normalized);
  return Number.isFinite(value) ? value : null;
}

function computeDiscount(regularPrice, price) {
  if (!regularPrice || !price || regularPrice <= 0) return null;
  const percent = ((regularPrice - price) / regularPrice) * 100;
  return Math.round(percent);
}

async function scrapePage(page, pageNumber) {
  const url = `${BASE_URL}${pageNumber}`;
  console.log(`➡️  Visiting page ${pageNumber}: ${url}`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await delay(2500 + Math.floor(Math.random() * 800));

  const products = await page.$$eval('div.product-tile, div.product-tile.js-product-tile', (tiles) => {
    return tiles
      .map((tile) => {
        const getText = (selector) => tile.querySelector(selector)?.textContent?.trim() || '';
        const linkEl = tile.querySelector('a[href]');
        const imgEl = tile.querySelector('img');
        const priceText =
          getText('.product-tile__price-current') ||
          getText('.product-tile__price .money') ||
          getText('.product-tile__price');
        const regularText =
          getText('.product-tile__price-regular') ||
          getText('.product-tile__price--compare') ||
          getText('.price__regular .money');

        return {
          sku: tile.getAttribute('data-product-sku') || tile.getAttribute('data-sku') || tile.dataset?.productSku || '',
          title:
            getText('.product-tile__title') ||
            getText('.product-tile__name') ||
            getText('[data-product-title]') ||
            getText('h3, h2'),
          imageUrl: imgEl?.getAttribute('src') || imgEl?.getAttribute('data-src') || '',
          productUrl: linkEl?.href || '',
          priceText,
          regularText,
        };
      })
      .filter((item) => item && (item.title || item.priceText));
  });

  const normalized = products
    .map((item) => {
      const price = parsePrice(item.priceText);
      const regularPrice = parsePrice(item.regularText);
      const discountPercent = computeDiscount(regularPrice, price);
      return {
        sku: item.sku,
        title: item.title,
        imageUrl: item.imageUrl,
        productUrl: item.productUrl,
        price,
        regularPrice,
        discountPercent,
      };
    })
    .filter((item) => item.title && Number.isFinite(item.price));

  console.log(`   ↳ Found ${normalized.length} products on page ${pageNumber}`);
  return normalized;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({});
  const page = await context.newPage();
  const productMap = new Map();

  try {
    for (let pageNumber = 1; pageNumber <= MAX_PAGES; pageNumber += 1) {
      const pageItems = await scrapePage(page, pageNumber);
      if (!pageItems.length) {
        console.log(`🚪 No products on page ${pageNumber}. Stopping pagination.`);
        break;
      }

      for (const product of pageItems) {
        const key = product.productUrl || `${product.sku}-${product.title}`;
        if (!key) continue;
        if (!productMap.has(key)) {
          productMap.set(key, product);
        }
      }
    }
  } catch (error) {
    console.error('❌ Error during scraping', error);
  } finally {
    await browser.close();
  }

  const uniqueProducts = Array.from(productMap.values());
  console.log(`📦 Total unique products: ${uniqueProducts.length}`);

  await fs.promises.mkdir(OUTPUT_DIR, { recursive: true });
  await fs.promises.writeFile(OUTPUT_FILE, JSON.stringify(uniqueProducts, null, 2), 'utf-8');
  console.log(`✅ Saved clearance data to ${OUTPUT_FILE}`);
}

main().catch((error) => {
  console.error('❌ Unexpected error', error);
  process.exit(1);
});
