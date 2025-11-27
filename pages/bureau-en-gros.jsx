// pages/bureau-en-gros.jsx

import fs from "fs";
import path from "path";

export async function getStaticProps() {
  const filePath = path.join(
    process.cwd(),
    "outputs",
    "bureauengros",
    "102-bureau-en-gros-welland-on",
    "data.json"
  );

  const raw = await fs.readFile(filePath, "utf-8");
  const parsed = JSON.parse(raw);

  return {
    props: {
      store: parsed.store ?? null,
      products: parsed.products ?? [],
    },
  };
}

export default function BureauEnGrosPage({ store, products }) {
  return (
    <main style={{ padding: "2rem", maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: "1.5rem" }}>
        <p style={{ color: "#666", margin: 0 }}>Liquidations</p>
        <h1 style={{ margin: "0.25rem 0" }}>{store?.name ?? "Bureau en Gros"}</h1>
        {store?.address && <p style={{ margin: 0 }}>{store.address}</p>}
        <p style={{ margin: "0.5rem 0 0", color: "#666" }}>
          {products.length} article{products.length > 1 ? "s" : ""} en liquidation
          à cette succursale.
        </p>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: "1rem",
        }}
      >
        {products.map((product) => (
          <article
            key={product.productUrl}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 12,
              padding: "1rem",
              background: "#fff",
              boxShadow: "0 4px 8px rgba(0,0,0,0.04)",
              display: "flex",
              flexDirection: "column",
              gap: "0.5rem",
            }}
          >
            {product.imageUrl && (
              <div
                style={{
                  width: "100%",
                  paddingTop: "65%",
                  position: "relative",
                  overflow: "hidden",
                  borderRadius: 8,
                  background: "#f9fafb",
                }}
              >
                <img
                  src={product.imageUrl}
                  alt={product.title}
                  style={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    objectFit: "contain",
                  }}
                />
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <h2 style={{ fontSize: "1rem", margin: 0, lineHeight: 1.4 }}>
                {product.title}
              </h2>
              {product.discountPercent != null && (
                <span
                  style={{
                    alignSelf: "flex-start",
                    background: "#dcfce7",
                    color: "#166534",
                    fontWeight: 600,
                    borderRadius: 6,
                    padding: "0.15rem 0.5rem",
                    fontSize: "0.9rem",
                  }}
                >
                  -{product.discountPercent}%
                </span>
              )}
              <p style={{ margin: 0, fontSize: "0.95rem" }}>
                <strong style={{ fontSize: "1.1rem" }}>
                  {product.currentPrice != null
                    ? `${product.currentPrice.toFixed(2)} $`
                    : "Prix non disponible"}
                </strong>
                {product.originalPrice && (
                  <span
                    style={{
                      marginLeft: 8,
                      color: "#6b7280",
                      textDecoration: "line-through",
                    }}
                  >
                    {product.originalPrice.toFixed(2)} $
                  </span>
                )}
              </p>
            </div>

            <a
              href={product.productUrl}
              style={{
                marginTop: "auto",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                padding: "0.55rem 0.85rem",
                borderRadius: 8,
                background: "#111827",
                color: "#fff",
                textDecoration: "none",
                fontWeight: 600,
              }}
              target="_blank"
              rel="noreferrer"
            >
              Voir le produit
            </a>
          </article>
        ))}
      </section>
    </main>
  );
}
