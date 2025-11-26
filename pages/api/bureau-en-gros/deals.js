// pages/api/bureau-en-gros/deals.js

import fs from "fs";
import path from "path";

export default function handler(req, res) {
  try {
    // On accepte ?store=... ou ?storeSlug=...
    const slug = req.query.store || req.query.storeSlug;

    if (!slug) {
      return res.status(400).json({
        error: "Missing required query param: 'store' (or 'storeSlug')",
      });
    }

    // Dossier réel dans le repo :
    // outputs/bureauengros/<slug>/data.json
    const baseDir = path.join(process.cwd(), "outputs", "bureauengros");
    const jsonPath = path.join(baseDir, slug, "data.json");

    if (!fs.existsSync(jsonPath)) {
      return res.status(404).json({
        error: "Store JSON file not found",
        slug,
        jsonPath,
      });
    }

    const raw = fs.readFileSync(jsonPath, "utf8");
    const deals = JSON.parse(raw);

    return res.status(200).json({
      store: slug,
      count: Array.isArray(deals) ? deals.length : 0,
      deals,
    });
  } catch (err) {
    console.error("[BUREAU-EN-GROS API ERROR]", err);
    return res.status(500).json({
      error: "Internal server error",
      message: err.message,
    });
  }
}
