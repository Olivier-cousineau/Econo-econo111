import { readBureauEnGrosDealsForAllStores } from './server/bureauEnGrosData';

export function readBureauEnGrosDeals(slug) {
  const products = readBureauEnGrosDealsForAllStores(slug);
  return { store: slug ?? null, products };
}
