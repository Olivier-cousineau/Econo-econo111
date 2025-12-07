import type { NextApiRequest, NextApiResponse } from "next";
import { readBestBuyDeals } from "../../lib/bestbuy";

export default function handler(req: NextApiRequest, res: NextApiResponse) {
  try {
    const deals = readBestBuyDeals();

    res.status(200).json({
      ok: true,
      count: deals.length,
      sample: deals.slice(0, 5),
    });
  } catch (error: any) {
    console.error("[BestBuy debug] Failed to load deals:", error);
    res.status(500).json({
      ok: false,
      error: error?.message ?? "Unknown error",
    });
  }
}
