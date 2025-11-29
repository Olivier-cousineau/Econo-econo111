// pages/bureau-en-gros/[storeSlug].tsx
import fs from "fs";
import path from "path";
import Link from "next/link";

const ROOT_DIR = process.cwd();
const BUREAU_PUBLIC_DIR = path.join(ROOT_DIR, "public", "bureauengros");

// Lit le fichier JSON d'un magasin (coté serveur seulement)
function readStoreDeals(storeSlug: string) {
  const filePath = path.join(BUREAU_PUBLIC_DIR, storeSlug, "data.json");

  if (!fs.existsSync(filePath)) {
    return null;
  }

  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw);
}

export async function getStaticPaths() {
  const entries = fs.readdirSync(BUREAU_PUBLIC_DIR, { withFileTypes: true });

  const paths = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      params: { storeSlug: entry.name },
    }));

  return {
    paths,
    fallback: false,
  };
}

export async function getStaticProps({ params }: { params: { storeSlug: string } }) {
  const storeSlug = params.storeSlug;
  const deals = readStoreDeals(storeSlug);

  // fallback de sécurité si jamais le fichier n'existe pas
  const safeDeals =
    deals && typeof deals === "object"
      ? deals
      : {
          storeId: storeSlug,
          storeName: storeSlug.replace(/-/g, " "),
          url: "",
          scrapedAt: null,
          count: 0,
          products: [],
        };

  return {
    props: {
      storeSlug,
      deals: safeDeals,
    },
    // ISR: on rafraîchit toutes les 15 minutes
    revalidate: 900,
  };
}

type Product = {
  title: string;
  productUrl: string;
  currentPrice?: number | null;
  originalPrice?: number | null;
  discountPercent?: number | null;
  imageUrl?: string | null;
};

export default function BureauEnGrosStorePage({
  storeSlug,
  deals,
}: {
  storeSlug: string;
  deals: {
    storeName?: string;
    count?: number;
    products: Product[];
  };
}) {
  const products = deals.products || [];
  const title =
    deals.storeName || storeSlug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const total = deals.count ?? products.length;

  return (
    <main className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold mb-2">Bureau en Gros – {title}</h1>

      <p className="mb-4 text-sm text-gray-600">
        {total} articles en liquidation (tous les rabais, pas seulement -50%).
      </p>

      <Link href="/bureau-en-gros" className="text-sm underline mb-4 inline-block">
        ← Retour à la liste des magasins
      </Link>

      {products.length === 0 && (
        <p className="mt-4">Aucune liquidation trouvée pour ce magasin.</p>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((p, idx) => (
          <article
            key={`${p.productUrl}-${idx}`}
            className="border rounded-lg p-3 flex flex-col bg-white shadow-sm"
          >
            {p.imageUrl && (
              <img
                src={p.imageUrl}
                alt={p.title}
                className="w-full h-40 object-contain mb-2"
                loading="lazy"
              />
            )}

            <h2 className="font-semibold mb-1 text-sm line-clamp-3">{p.title}</h2>

            {typeof p.currentPrice === "number" && (
              <p className="font-bold text-base mt-1">
                {p.currentPrice.toFixed(2)} $
                {typeof p.originalPrice === "number" &&
                  p.originalPrice > p.currentPrice && (
                    <span className="ml-2 line-through text-xs text-gray-500">
                      {p.originalPrice.toFixed(2)} $
                    </span>
                  )}
              </p>
            )}

            {typeof p.discountPercent === "number" && (
              <p className="text-xs text-green-700 font-semibold mt-1">
                -{p.discountPercent}% de rabais
              </p>
            )}

            <a
              href={p.productUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-auto text-sm text-blue-600 underline pt-2"
            >
              Voir sur Bureau en Gros
            </a>
          </article>
        ))}
      </div>
    </main>
  );
}
