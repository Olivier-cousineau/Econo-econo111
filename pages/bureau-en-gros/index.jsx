import Link from "next/link";
import { buildBureauEnGrosStore } from "../../lib/bureauEnGrosDeals";

export const getStaticProps = async () => {
  const fs = await import("fs");
  const path = await import("path");

  const rootDir = process.cwd();
  const baseDir = path.join(rootDir, "outputs", "bureauengros");

  let stores = [];

  if (!fs.existsSync(baseDir)) {
    console.warn("[BureauEnGros] outputs/bureauengros directory not found:", baseDir);
  } else {
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });

    stores = entries
      .filter((entry) => entry.isDirectory())
      .map((entry) => {
        const slug = entry.name;
        const folderPath = path.join(baseDir, slug);
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
          console.warn(
            "[BureauEnGros] Failed to read JSON for store:",
            slug,
            jsonPath,
            error,
          );
        }

        return buildBureauEnGrosStore(slug, productCount, jsonPath);
      })
      .filter(Boolean)
      .sort((a, b) => a.id.localeCompare(b.id));
  }

  return {
    props: {
      stores,
    },
  };
};

export default function BureauEnGrosIndexPage({ stores }) {
  return (
    <main style={{ padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
      <h1>Bureau en Gros – Liquidations</h1>
      <p>
        Toutes les liquidations chargées depuis{" "}
        <code>outputs/bureauengros/**/data.json</code>.
      </p>

      {stores.length === 0 && (
        <p>Aucun magasin Bureau en Gros trouvé dans outputs/bureauengros.</p>
      )}

      <ul>
        {stores.map((store) => (
          <li key={store.slug} style={{ margin: "0.5rem 0" }}>
            <Link href={`/bureau-en-gros/${store.slug}`}>
              {store.label}{" "}
              <span style={{ opacity: 0.7 }}>
                ({store.productCount} produits)
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
