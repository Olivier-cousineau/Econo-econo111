// pages/bureau-en-gros/index.jsx

import fs from "fs";
import path from "path";
import Link from "next/link";

const slugToLabel = (slug) => {
  const [storeIdFromSlug, ...citySegments] = slug.split("-");
  const citySlug = citySegments.join("-");
  const cityLabel = citySlug ? citySlug.replace(/-/g, " ") : "Unknown";
  const storeId = storeIdFromSlug ?? slug;
  return {
    storeId,
    city: cityLabel,
    label: `${storeId} – ${cityLabel}`,
  };
};

export const getStaticProps = async () => {
  // 🔥 IMPORTANT : bon dossier de sortie pour Bureau en Gros
  const outputsRoot = path.join(process.cwd(), "outputs", "bureauengros");
  let dirEntries = [];

  try {
    dirEntries = await fs.promises.readdir(outputsRoot, {
      withFileTypes: true,
    });
  } catch (error) {
    console.error("Unable to read outputs/bureauengros directory", error);
    return {
      props: { stores: [] },
      revalidate: 300,
    };
  }

  const stores = [];

  for (const entry of dirEntries) {
    if (!entry.isDirectory()) continue;

    const dataPath = path.join(outputsRoot, entry.name, "data.json");
    if (!fs.existsSync(dataPath)) {
      // on ignore silencieusement les magasins sans fichier
      continue;
    }

    try {
      const fileContents = await fs.promises.readFile(dataPath, "utf-8");
      const parsed = JSON.parse(fileContents);
      const products = Array.isArray(parsed) ? parsed : [];
      if (products.length === 0) continue;

      const { storeId, city, label } = slugToLabel(entry.name);
      stores.push({
        storeSlug: entry.name,
        storeId,
        city,
        label,
        productCount: products.length,
      });
    } catch (error) {
      console.warn(
        `Skipping ${entry.name} because data.json is invalid or unreadable`,
        error
      );
      continue;
    }
  }

  stores.sort((a, b) => a.label.localeCompare(b.label));

  return {
    props: { stores },
    revalidate: 300,
  };
};

const BureauEnGrosIndexPage = ({ stores }) => {
  return (
    <main style={{ padding: "2rem 1rem", maxWidth: "1100px", margin: "0 auto" }}>
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>
          Bureau en Gros – Produits en liquidation
        </h1>
        <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>
          Sélectionne un magasin ci-dessous pour voir les produits en liquidation
          disponibles à cet endroit. Les produits sont chargés seulement quand tu
          ouvres une page de magasin.
        </p>
      </header>

      {stores.length === 0 ? (
        <p>
          Aucun magasin Bureau en Gros n’a encore de données dans les outputs.
          Vérifie que le scraper a bien écrit dans <code>outputs/bureauengros</code>.
        </p>
      ) : (
        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {stores.map((store) => (
            <article
              key={store.storeSlug}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: "0.75rem",
                padding: "1.25rem",
                background: "#fff",
                boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              <div style={{ fontSize: "0.9rem", color: "#6b7280" }}>
                Magasin #{store.storeId}
              </div>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 600 }}>{store.city}</h2>
              <div style={{ fontSize: "0.95rem", color: "#1f2937" }}>
                {store.productCount.toLocaleString()} produits en liquidation
              </div>
              <Link
                href={`/bureau-en-gros/${store.storeSlug}`}
                style={{
                  marginTop: "auto",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "0.65rem 1rem",
                  borderRadius: "999px",
                  backgroundColor: "#2563eb",
                  color: "#fff",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                Voir les produits
              </Link>
            </article>
          ))}
        </section>
      )}
    </main>
  );
};

export default BureauEnGrosIndexPage;
