import { loadCanadianTireDeals } from './canadianTireDeals';
import { loadBureauEnGrosDeals } from './bureauEnGrosDeals';

export async function getDeals(params) {
  const { retailer, ...rest } = params;

  // Canadian Tire
  if (retailer === 'canadian-tire') {
    return await loadCanadianTireDeals(rest);
  }

  // Bureau en Gros
  if (retailer === 'bureau-en-gros') {
    return await loadBureauEnGrosDeals(rest);
  }

  // Default empty result
  return [];
}
