// lib/bestbuyClearance.js
// --------------------------------------------
// Lecture des liquidations Best Buy à partir du
// fichier public/bestbuy/clearance.json
// --------------------------------------------

import fs from "fs";
import path from "path";

// On pointe maintenant vers le fichier SERVI par Vercel :
//   public/bestbuy/clearance.json
const CLEARANCE_PATH = path.join(
  process.cwd(),
  "public",
  "bestbuy",
  "clearance.json"
);

/**
 * Essaie d’extraire un prix numérique.
 * - Si item.price est déjà un nombre → on le retourne.
 * - Sinon, on essaie de lire item.price_raw et de garder seulement les chiffres.
 */
function normalizePrice(item) {
  if (typeof item?.price === "number") {
    return item.price;
  }

  if (typeof item?.price_raw === "string") {
    const numeric = parseFloat(item.price_raw.replace(/[^0-9.]/g, ""));
    return Number.isFinite(numeric) ? numeric : null;
  }

  return null;
}

/**
 * Lit le fichier de liquidations Best Buy et retourne un tableau d’objets normalisés.
 *
 * Retourne toujours un tableau (jamais null) pour simplifier le code du front.
 */
export function readBestBuyClearanceDeals() {
  try {
    // Vérifie d’abord que le fichier existe
    if (!fs.existsSync(CLEARANCE_PATH)) {
      console.error(
        "[BestBuy] clearance.json introuvable à ce chemin :",
        CLEARANCE_PATH
      );
      return [];
    }

    const content = fs.readFileSync(CLEARANCE_PATH, "utf8");
    const data = JSON.parse(content);

    if (!Array.isArray(data)) {
      console.error(
        "[BestBuy] Le contenu de clearance.json n’est pas un tableau."
      );
      return [];
    }

    // Normalisation des données pour le front
    return data.map((item, index) => {
      const title =
        typeof item?.title === "string" && item.title.trim()
          ? item.title.trim()
          : `Produit ${index + 1}`;

      const url = typeof item?.url === "string" ? item.url : "";

      return {
        title,
        url,
        price: normalizePrice(item),
        priceRaw: typeof item?.price_raw === "string" ? item.price_raw : "",
      };
    });
  } catch (error) {
    console.error("[BestBuy] Échec de la lecture des liquidations Best Buy :", error);
    return [];
  }
}
