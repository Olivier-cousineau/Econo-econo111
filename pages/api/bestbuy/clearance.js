import { readBestBuyClearanceDeals } from "../../../lib/bestbuyClearance";

export default function handler(req, res) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const deals = readBestBuyClearanceDeals();

  res.status(200).json({
    ok: true,
    source: "/outputs/bestbuy/clearance.json",
    count: deals.length,
    deals,
    items: deals,
  });
}
