// pages/bureau-en-gros/[storeSlug].tsx
import fs from "fs";
import path from "path";
import { GetStaticPaths, GetStaticProps } from "next";

type Product = {
  title: string;
  productUrl: string;
  currentPrice: number | null;
  originalPrice: number | null;
  discountPercent: number | null;
  imageUrl: string | null;
};

type StorePageProps = {
  storeId: number;
  storeName: string;
  sourceStore: string;
  count: number;
  products: Product[];
  storeSlug: string;
};

const BUREAU_ROOT = path.join(process.cwd(), "public", "bureauengros");

export const getStaticPaths: GetStaticPaths = async () => {
  // 🔹 Pour l’instant on génère SEULEMENT Saint-Jérôme
  const storeSlugs = ["124-bureau-en-gros-saint-jerome-qc"];

  const paths = storeSlugs.map((slug) => ({
    params: { storeSlug: slug },
  }));

  return {
    paths,
    fallback: false, // 404 pour tout le reste (normal pour l’instant)
  };
};

export const getStaticProps: GetStaticProps<StorePageProps> = async (context) => {
  const storeSlug = context.params?.storeSlug;

  if (typeof storeSlug !== "string") {
    throw new Error("Invalid storeSlug");
  }

  const jsonPath = path.join(BUREAU_ROOT, storeSlug, "data.json");

  if (!fs.existsSync(jsonPath)) {
    throw new Error(`File not found for storeSlug: ${storeSlug} at ${jsonPath}`);
  }

  const raw = fs.readFileSync(jsonPath, "utf-8");
  const parsed = JSON.parse(raw);

  return {
    props: {
      storeId: parsed.storeId ?? 0,
      storeName: parsed.storeName ?? "Bureau en Gros",
      sourceStore: parsed.sourceStore ?? "",
      count: parsed.count ?? 0,
      products: parsed.products ?? [],
      storeSlug,
    },
    revalidate: 300, // 5 minutes
  };
};

export default function BureauEnGrosStorePage(props: StorePageProps) {
  const { storeName, count, products } = props;

  return (
    <main style={{ padding: "20px", maxWidth: "1200px", margin: "0 auto" }}>
      <h1>Bureau en Gros – {storeName}</h1>
      <p style={{ marginTop: "8px" }}>
        <strong>{count}</strong> produits en liquidation trouvés.
      </p>

      {products.length === 0 && <p>Aucune liquidation pour ce magasin.</p>}

      <div
        style={{
          marginTop: "24px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: "16px",
        }}
      >
        {products.map((p, index) => (
          <article
            key={`${p.productUrl}-${index}`}
            style={{
              border: "1px solid #ddd",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            {p.imageUrl && (
              <div style={{ textAlign: "center", marginBottom: "8px" }}>
                <img
                  src={p.imageUrl}
                  alt={p.title}
                  style={{ maxWidth: "100%", maxHeight: "150px", objectFit: "contain" }}
                />
              </div>
            )}
            <h2 style={{ fontSize: "16px", marginBottom: "6px" }}>{p.title}</h2>
            <p style={{ margin: "4px 0" }}>
              Prix actuel:{" "}
              {p.currentPrice != null ? `${p.currentPrice.toFixed(2)} $` : "N/A"}
            </p>
            <p style={{ margin: "4px 0" }}>
              Prix original:{" "}
              {p.originalPrice != null ? `${p.originalPrice.toFixed(2)} $` : "N/A"}
            </p>
            <p style={{ margin: "4px 0" }}>
              Rabais:{" "}
              {p.discountPercent != null ? `${p.discountPercent}%` : "N/A"}
            </p>
            <a
              href={p.productUrl}
              target="_blank"
              rel="noreferrer"
              style={{ color: "#0070f3", textDecoration: "underline", fontSize: "14px" }}
            >
              Voir le produit
            </a>
          </article>
        ))}
      </div>
    </main>
  );
}
