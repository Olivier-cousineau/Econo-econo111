// lib/deals.js
import { loadCanadianTireDeals } from './canadianTireDeals';
import { loadBureauEnGrosDeals } from './bureauEnGrosDeals';

/**
 * Router générique pour les deals.
 * params doit contenir au minimum { retailer, store, minDiscount? }
 */
export async function getDeals(params) {
  const { retailer, ...rest } = params || {};

  // Canadian Tire
  if (retailer === 'canadian-tire') {
    return await loadCanadianTireDeals(rest);
  }

  // Bureau en Gros
  if (retailer === 'bureau-en-gros') {
    return await loadBureauEnGrosDeals(rest);
  }

  // Retailer inconnu -> aucun résultat
  return [];
}
