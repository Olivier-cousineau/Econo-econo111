import { readBestBuyDeals } from "../../../lib/bestbuy";

export default function handler(req, res) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const deals = readBestBuyDeals();

  res.status(200).json({
    ok: true,
    source: "/outputs/bestbuy/clearance.json",
    count: deals.length,
    deals,
    items: deals,
  });
}
