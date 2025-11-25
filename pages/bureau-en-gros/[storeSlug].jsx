import Link from "next/link";
import {
  buildBureauEnGrosStore,
  filterVisibleBureauEnGrosDeals,
} from "../../lib/bureauEnGrosDeals";

export const getStaticPaths = async () => {
  const fs = await import("fs");
  const path = await import("path");

  const baseDir = path.join(process.cwd(), "outputs", "bureauengros");

  let slugs = [];

  if (fs.existsSync(baseDir)) {
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });
    slugs = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);
  }

  return {
    paths: slugs.map((slug) => ({ params: { storeSlug: slug } })),
    fallback: "blocking",
  };
};

export const getStaticProps = async (ctx) => {
  const fs = await import("fs");
  const path = await import("path");

  const slug = ctx.params?.storeSlug;
  const baseDir = path.join(process.cwd(), "outputs", "bureauengros");
  const jsonPath = path.join(baseDir, slug, "data.json");

  if (!fs.existsSync(jsonPath)) {
    return {
      notFound: true,
    };
  }

  let deals = [];

  try {
    const raw = fs.readFileSync(jsonPath, "utf8");
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      deals = parsed;
    } else {
      console.warn(
        "[BureauEnGros] JSON is not an array for store",
        slug,
        jsonPath,
      );
    }
  } catch (err) {
    console.error(
      "[BureauEnGros] Failed to read data.json for store",
      slug,
      jsonPath,
      err,
    );
  }

  const visibleDeals = filterVisibleBureauEnGrosDeals(deals);
  const store = buildBureauEnGrosStore(slug, deals.length, jsonPath);

  console.log(
    `[DEBUG] Bureau en Gros store ${slug}: total deals = ${deals.length}, visible = ${visibleDeals.length}`,
  );

  return {
    props: {
      store,
      deals: visibleDeals,
    },
  };
};

export default function BureauEnGrosStorePage({ store, deals }) {
  return (
    <main style={{ padding: "2rem", maxWidth: 1000, margin: "0 auto" }}>
      <p>
        <Link href="/bureau-en-gros">← Retour à la liste des magasins</Link>
      </p>

      <h1>{store.label}</h1>
      <p>
        Fichier : <code>{store.jsonPath}</code>
      </p>
      <p>
        Nombre de produits affichés : <strong>{deals.length}</strong>
      </p>

      {deals.length === 0 && (
        <p>
          Aucun produit valide trouvé dans ce fichier. Vérifie que le data.json
          contient bien un tableau d&apos;objets avec au moins
          <code>title</code> et <code>priceCurrent</code>.
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))",
          gap: "1rem",
          marginTop: "1rem",
        }}
      >
        {deals.map((deal, idx) => (
          <article
            key={idx}
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: "0.75rem",
            }}
          >
            {deal.imageUrl && (
              <div style={{ textAlign: "center", marginBottom: "0.5rem" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={deal.imageUrl}
                  alt={deal.title ?? ""}
                  style={{ maxWidth: "100%", maxHeight: 160, objectFit: "contain" }}
                />
              </div>
            )}
            <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
              {deal.title ?? "Sans titre"}
            </h2>
            <p>
              <strong>Prix actuel : </strong>
              {deal.priceCurrent}
            </p>
            {deal.priceOriginal && (
              <p>
                <strong>Prix original : </strong>
                <span style={{ textDecoration: "line-through" }}>
                  {deal.priceOriginal}
                </span>
              </p>
            )}
            {typeof deal.discountPercent === "number" && (
              <p>
                <strong>Rabais : </strong>
                {deal.discountPercent}%
              </p>
            )}
            {deal.url && (
              <p>
                <a href={deal.url} target="_blank" rel="noreferrer">
                  Voir le produit
                </a>
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
