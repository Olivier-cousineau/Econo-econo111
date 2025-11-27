// lib/bureauEnGrosDeals.js
import {
  listBureauEnGrosStoreSlugs,
  readBureauEnGrosDealsForAllStores,
} from './bureauEngros';

/**
 * Charge les deals Bureau en Gros à partir de la source Saint-Jérôme.
 * Le même contenu est utilisé pour tous les magasins.
 */
export async function loadBureauEnGrosDeals({ store, minDiscount = 0 }) {
  try {
    const storeSlugs = listBureauEnGrosStoreSlugs();

    if (storeSlugs.length > 0 && store && !storeSlugs.includes(store)) {
      console.warn('loadBureauEnGrosDeals: store slug not found in outputs', store);
      return [];
    }

    const products = readBureauEnGrosDealsForAllStores();

    if (!Array.isArray(products) || products.length === 0) {
      return [];
    }

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
    console.error(`Error loading Bureau en Gros deals:`, err);
    return [];
  }
}
