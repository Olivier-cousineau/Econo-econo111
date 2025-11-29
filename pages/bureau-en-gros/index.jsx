// pages/bureau-en-gros/index.jsx

import Link from "next/link";
import { getBureauEnGrosStores } from "../../lib/bureauEngros";
import { readBureauEnGrosDealsForStore } from "../../lib/server/bureauEnGrosData";

export const getStaticProps = async () => {
  const stores = getBureauEnGrosStores().map((store) => {
    const deals = readBureauEnGrosDealsForStore(store.slug);
    return {
      storeSlug: store.slug,
      storeId: store.id,
      city: store.city,
      name: store.name,
      address: store.address,
      productCount: deals.length,
    };
  });

  stores.sort((a, b) => a.name.localeCompare(b.name));

  const totalProducts = stores.reduce(
    (sum, store) => sum + (store.productCount || 0),
    0
  );

  return {
    props: {
      stores,
      totalProducts,
    },
    revalidate: 300,
  };
};

const BureauEnGrosIndexPage = ({ stores, totalProducts }) => {
  return (
    <main style={{ padding: "2rem 1rem", maxWidth: "1100px", margin: "0 auto" }}>
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2rem", fontWeight: 700 }}>
          Bureau en Gros – Produits en liquidation
        </h1>
        <p style={{ marginTop: "0.5rem", color: "#4b5563" }}>
          Sélectionne un magasin ci-dessous pour voir les produits en
          liquidation. Les données proviennent de fichiers JSON générés par ton
          scraper.
        </p>
        <p style={{ marginTop: "0.25rem", color: "#6b7280" }}>
          Total de produits indexés : <strong>{totalProducts}</strong>
        </p>
      </header>

      {stores.length === 0 ? (
        <p>Aucun magasin Bureau en Gros n’est encore configuré.</p>
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
              <h2 style={{ fontSize: "1rem", fontWeight: 600 }}>
                {store.name}
              </h2>
              <p style={{ fontSize: "0.9rem", color: "#4b5563" }}>
                {store.address}
              </p>
              <p style={{ fontSize: "0.9rem" }}>
                <strong>{store.productCount}</strong> produit(s) en liquidation
                dans ce magasin.
              </p>
              <div style={{ marginTop: "auto" }}>
                <Link
                  href={`/bureau-en-gros/${store.storeSlug}`}
                  style={{
                    display: "inline-block",
                    marginTop: "0.75rem",
                    padding: "0.5rem 0.9rem",
                    borderRadius: "0.5rem",
                    border: "1px solid #2563eb",
                    color: "#2563eb",
                    fontSize: "0.9rem",
                    fontWeight: 500,
                  }}
                >
                  Voir les liquidations
                </Link>
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
};

export default BureauEnGrosIndexPage;
