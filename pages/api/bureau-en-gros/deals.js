// pages/api/bureau-en-gros/deals.js

import fs from "fs";
import path from "path";

export default function handler(req, res) {
  try {
    const { storeSlug } = req.query;

    if (!storeSlug) {
      return res
        .status(400)
        .json({ error: "Missing required query param: storeSlug" });
    }

    // IMPORTANT : dossier réel sur le repo
    // /outputs/bureauengros/<store-slug>/data.json
    const baseDir = path.join(process.cwd(), "outputs", "bureauengros");
    const jsonPath = path.join(baseDir, storeSlug, "data.json");

    if (!fs.existsSync(jsonPath)) {
      return res.status(404).json({
        error: "Store JSON file not found",
        jsonPath,
      });
    }

    const raw = fs.readFileSync(jsonPath, "utf8");
    const deals = JSON.parse(raw);

    // Tu peux ajouter des filtres ici si tu veux (minDiscount, search, etc.)
    // Pour l’instant, on renvoie tout tel quel pour vérifier que ça marche.
    return res.status(200).json({
      storeSlug,
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
