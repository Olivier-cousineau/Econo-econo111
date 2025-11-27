// lib/bureauEnGrosDeals.js
import fs from 'fs';
import path from 'path';

const OUTPUTS_ROOT = path.join(process.cwd(), 'outputs', 'bureauengros');

/**
 * Charge les deals pour un magasin Bureau en Gros donné.
 *
 * @param {Object} params
 * @param {string} params.store  - slug du magasin (ex: "124-bureau-en-gros-saint-jerome-qc")
 * @param {number} [params.minDiscount=0] - rabais minimal en %
 */
export async function loadBureauEnGrosDeals({ store, minDiscount = 0 }) {
  try {
    if (!store) {
      console.warn('loadBureauEnGrosDeals: store slug is missing');
      return [];
    }

    const storePath = path.join(OUTPUTS_ROOT, store, 'data.json');

    if (!fs.existsSync(storePath)) {
      console.warn(`No Bureau en Gros data found for store: ${store}`);
      return [];
    }

    const raw = await fs.promises.readFile(storePath, 'utf-8');
    const products = JSON.parse(raw);

    // On attend un tableau de produits
    if (!Array.isArray(products)) {
      console.warn(
        `Invalid Bureau en Gros data format for store: ${store}, expected array`
      );
      return [];
    }

    // Filtre sur le rabais minimal si dispo
    return products.filter((p) => {
      const discount =
        typeof p.discount === 'number'
          ? p.discount
          : typeof p.discountPercent === 'number'
          ? p.discountPercent
          : 0;

      return discount >= minDiscount;
    });
  } catch (err) {
    console.error(`Error loading Bureau en Gros deals for store ${store}:`, err);
    return [];
  }
}
