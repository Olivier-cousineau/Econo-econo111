// pages/api/bureau-en-gros/deals.js

import dealsHandler from '../deals';

// On réutilise la même logique que /api/deals,
// mais on force juste retailer = "bureau-en-gros" si non fourni.
export default function handler(req, res) {
  if (!req.query.retailer) {
    req.query.retailer = 'bureau-en-gros';
  }
  return dealsHandler(req, res);
}
