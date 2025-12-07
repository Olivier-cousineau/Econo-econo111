import { NextApiRequest, NextApiResponse } from "next";
import { readBestBuyDeals } from "../../lib/bestbuy";

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "GET") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const deals = readBestBuyDeals();

  res.status(200).json({
    count: deals.length,
    sample: deals.slice(0, 5),
  });
}
