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

// 🔹 Pour l’instant on ne build que Saint-Jérôme
export const getStaticPaths: GetStaticPaths = async () => {
  const storeSlugs = ["124-bureau-en-gros-saint-jerome-qc"];

  const paths = storeSlugs.map((slug) => ({
    params: { storeSlug: slug },
  }));

  return {
    paths,
    fallback: false,
  };
};

function parsePrice(raw: unknown): number | null {
  if (raw == null) return null;
  const s = String(raw)
    .replace(/[^\d.,-]/g, "")
    .replace(",", ".");
  const n = parseFloat(s);
  return Number.isNaN(n) ? null : n;
}

function computeDiscount(currentPrice: number | null, originalPrice: number | null): number | null {
  if (
    currentPrice == null ||
    originalPrice == null ||
    currentPrice <= 0 ||
    originalPrice <= 0 ||
    currentPrice >= originalPrice
  ) {
    return null;
  }
  return Math.round(((originalPrice - currentPrice) / originalPrice) * 100);
}

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

  // 🔹 Cas 1 : ton fichier est une LISTE d’objets (format actuel)
  let productsSource: any[] = [];
  let storeName = "Bureau en Gros – Saint-Jérôme, QC";
  let storeId = 124;
  let sourceStore = "Saint-Jérôme";

  if (Array.isArray(parsed)) {
    productsSource = parsed;
  } else if (parsed && typeof parsed === "object" && Array.isArray(parsed.products)) {
    // 🔹 Cas 2 : plus tard, si tu utilises un objet { storeId, storeName, products: [...] }
    productsSource = parsed.products;
    storeName = parsed.storeName ?? storeName;
    storeId = parsed.storeId ?? storeId;
    sourceStore = parsed.sourceStore ?? sourceStore;
  }

  const products: Product[] = productsSource.map((item, index) => {
    const title =
      item.title ||
      item.product_name ||
      `Produit #${index + 1}`;

    const productUrl = item.productUrl || item.product_link || "";

    const currentPrice =
      typeof item.currentPrice === "number"
        ? item.currentPrice
        : parsePrice(item.discount_price ?? item.current_price);

    const originalPrice =
      typeof item.originalPrice === "number"
        ? item.originalPrice
        : parsePrice(item.original_price ?? item.regular_price);

    const discountPercent =
      typeof item.discountPercent === "number"
        ? item.discountPercent
        : computeDiscount(currentPrice, originalPrice);

    const imageUrl = item.imageUrl || item.image_url || null;

    return {
      title,
      productUrl,
      currentPrice,
      originalPrice,
      discountPercent,
      imageUrl,
    };
  });

  return {
    props: {
      storeId,
      storeName,
      sourceStore,
      count: products.length,
      products,
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
