import fs from "fs";
import path from "path";
import Link from "next/link";
import { buildBureauEnGrosStore } from "../../lib/bureauEnGrosDeals";

const OUTPUT_DIR = path.join(process.cwd(), "outputs", "bureauengros");

async function loadStores() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    console.warn("[BureauEnGros] outputs/bureauengros directory not found:", OUTPUT_DIR);
    return [];
  }

  const entries = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true });

  return entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const slug = entry.name;
      const folderPath = path.join(OUTPUT_DIR, slug);
      const jsonPath = path.join(folderPath, "data.json");

      if (!fs.existsSync(jsonPath)) {
        return null;
      }

      let productCount = 0;

      try {
        const raw = fs.readFileSync(jsonPath, "utf8");
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          productCount = parsed.length;
        }
      } catch (error) {
        console.warn("[BureauEnGros] Failed to read JSON for store:", slug, jsonPath, error);
      }

      const store = buildBureauEnGrosStore(slug, productCount, jsonPath);

      return {
        slug: store.slug,
        label: store.label,
        productCount: store.productCount,
      };
    })
    .filter((value) => Boolean(value))
    .sort((a, b) => a.slug.localeCompare(b.slug));
}

export default async function BureauEnGrosIndexPage() {
  const stores = await loadStores();

  return (
    <main style={{ padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
      <h1>Bureau en Gros – Liquidations</h1>
      <p>
        Toutes les liquidations chargées depuis <code>outputs/bureauengros/**/data.json</code>.
      </p>

      {stores.length === 0 && (
        <p>Aucun magasin Bureau en Gros trouvé dans outputs/bureauengros.</p>
      )}

      <ul>
        {stores.map((store) => (
          <li key={store.slug} style={{ margin: "0.5rem 0" }}>
            <Link href={`/bureau-en-gros/${store.slug}`}>
              {store.label} <span style={{ opacity: 0.7 }}>({store.productCount} produits)</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
