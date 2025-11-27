// pages/bureau-en-gros.jsx

import fs from "fs";
import path from "path";

export async function getStaticProps() {
  const baseDir = path.join(process.cwd(), "outputs", "bureauengros");

  let stores = [];

  try {
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue; // un dossier = un magasin

      const slug = entry.name;
      const filePath = path.join(baseDir, slug, "data.json");

      try {
        const raw = fs.readFileSync(filePath, "utf-8");
        const json = JSON.parse(raw);

        const storeMeta = json.store || {};
        const products = Array.isArray(json.products) ? json.products : [];

        console.log(
          "[Bureau en Gros] magasin:",
          slug,
          "- produits:",
          products.length
        );

        stores.push({
          slug,
          store: {
            id: storeMeta.id ?? null,
            name: storeMeta.name ?? slug,
            address: storeMeta.address ?? "",
          },
          // ⚠️ on envoie les produits tels quels
          products,
        });
      } catch (err) {
        if (err.code === "ENOENT") {
          console.warn("⚠️ Fichier manquant pour Bureau en Gros :", slug);
          continue;
        }
        console.error("Erreur en lisant", slug, err);
        continue;
      }
    }
  } catch (e) {
    console.error("Erreur en listant outputs/bureauengros :", e);
    stores = [];
  }

  // Nettoyage pour Next (sérialisable)
  const serializableStores = JSON.parse(JSON.stringify(stores));

  return {
    props: {
      stores: serializableStores,
    },
    revalidate: 300,
  };
}

export default function BureauEnGrosPage({ stores }) {
  const countStores = stores?.length ?? 0;

  return (
    <main
      style={{
        maxWidth: "1200px",
        margin: "0 auto",
        padding: "2rem 1rem",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <h1
        style={{
          fontSize: "2rem",
          fontWeight: "700",
          marginBottom: "0.5rem",
        }}
      >
        Liquidations Bureau en Gros
      </h1>

      <p style={{ marginBottom: "1.5rem" }}>
        Magasins suivis : <strong>{countStores}</strong>
      </p>

      {countStores === 0 && (
        <p>Aucune donnée de liquidation n&apos;a été trouvée pour le moment.</p>
      )}

      {stores.map((store) => (
        <section
          key={store.slug}
          style={{
            marginTop: "2rem",
            paddingTop: "1.5rem",
            borderTop: "1px solid #e5e5e5",
          }}
        >
          <h2
            style={{
              fontSize: "1.3rem",
              fontWeight: "600",
              marginBottom: "0.25rem",
            }}
          >
            {store.store?.name || store.slug}
          </h2>

          {store.store?.address && (
            <p style={{ marginBottom: "0.5rem", color: "#555" }}>
              {store.store.address}
            </p>
          )}

          <p style={{ marginBottom: "0.75rem" }}>
            Produits en liquidation :{" "}
            <strong>{store.products?.length ?? 0}</strong>
          </p>

          {(!store.products || store.products.length === 0) && (
            <p style={{ fontSize: "0.9rem", color: "#777" }}>
              Aucun produit en liquidation trouvé pour ce magasin.
            </p>
          )}

          {store.products && store.products.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                gap: "1rem",
                marginTop: "0.5rem",
              }}
            >
              {store.products.map((product, index) => (
                <article
                  key={`${store.slug}-${index}`}
                  style={{
                    border: "1px solid #e5e5e5",
                    borderRadius: "8px",
                    padding: "0.75rem",
                    background: "#fff",
                  }}
                >
                  {product.imageUrl && (
                    <div style={{ marginBottom: "0.5rem" }}>
                      <img
                        src={product.imageUrl}
                        alt={product.title || ""}
                        style={{
                          width: "100%",
                          height: "160px",
                          objectFit: "contain",
                        }}
                      />
                    </div>
                  )}

                  <h3
                    style={{
                      fontSize: "0.95rem",
                      fontWeight: "600",
                      marginBottom: "0.25rem",
                    }}
                  >
                    {product.title}
                  </h3>

                  <div
                    style={{
                      fontSize: "0.9rem",
                      marginBottom: "0.25rem",
                    }}
                  >
                    {product.currentPrice != null && (
                      <div>
                        Prix actuel :{" "}
                        <strong>
                          {product.currentPrice}
                          $
                        </strong>
                      </div>
                    )}

                    {product.originalPrice != null && (
                      <div
                        style={{
                          textDecoration: "line-through",
                          opacity: 0.7,
                        }}
                      >
                        Prix original : {product.originalPrice}$
                      </div>
                    )}

                    {product.discountPercent != null && (
                      <div>
                        Rabais : <strong>{product.discountPercent}%</strong>
                      </div>
                    )}
                  </div>

                  {product.productUrl && (
                    <a
                      href={product.productUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        display: "inline-block",
                        marginTop: "0.5rem",
                        fontSize: "0.85rem",
                      }}
                    >
                      Voir le produit
                    </a>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      ))}
    </main>
  );
}
