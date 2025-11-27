import { readBureauEnGrosDealsForAllStores } from './bureauEngros';

export function readBureauEnGrosDeals(slug) {
  const products = readBureauEnGrosDealsForAllStores();
  return { store: slug ?? null, products };
}
