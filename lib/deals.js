import { getDeals } from '../../lib/deals';

export default async function handler(req, res) {
  const params = {
    ...req.query,
    // tu peux ajouter store, minDiscount etc. ici
  };

  const deals = await getDeals(params);
  res.status(200).json(deals);
}
