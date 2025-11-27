// pages/bureau-en-gros/index.jsx

import Link from "next/link";
import {
  listBureauEnGrosStoreSlugs,
  readBureauEnGrosDealsForAllStores,
} from "../../lib/bureauEngros";

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
  const storeSlugs = listBureauEnGrosStoreSlugs();
  const deals = readBureauEnGrosDealsForAllStores();
  const productCount = deals.length;

  const stores = storeSlugs.map((slug) => {
    const { storeId, city, label } = slugToLabel(slug);
    return {
      storeSlug: slug,
      storeId,
      city,
      label,
      productCount,
    };
  });

  stores.sort((a, b) => a.label.localeCompare(b.label));

  return {
    props: { stores, productCount },
    revalidate: 300,
  };
};

const BureauEnGrosIndexPage = ({ stores, productCount }) => {
  return (
    <main style={{ padding: "2rem 1rem", maxWidth: "1100px", margin: "0 auto" }}>
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>
          Bureau en Gros – Produits en liquidation
        </h1>
        <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>
          Sélectionne un magasin ci-dessous pour voir les produits en liquidation.
          Toutes les pages de magasins affichent temporairement les mêmes données (Saint-Jérôme).
        </p>
      </header>

      {stores.length === 0 ? (
        <p>
          Aucun magasin Bureau en Gros n’est encore listé. Ajoute des dossiers dans
          <code> outputs/bureauengros </code> pour les générer.
        </p>
      ) : productCount === 0 ? (
        <p>Aucune liquidation trouvée dans le fichier source Saint-Jérôme.</p>
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
