// pages/bestbuy/index.tsx
import fs from "fs";
import path from "path";
import { GetStaticProps } from "next";

type BestBuyProduct = {
  sku?: string;
  title?: string;
  productUrl?: string;
  currentPrice?: number | null;
  originalPrice?: number | null;
  discountPercent?: number | null;
  imageUrl?: string | null;
  category?: string | null;
  brand?: string | null;
};

type BestBuyPageProps = {
  products: BestBuyProduct[];
};

export const getStaticProps: GetStaticProps<BestBuyPageProps> = async () => {
  const filePath = path.join(
    process.cwd(),
    "outputs",
    "bestbuy",
    "clearance.json"
  );

  let products: BestBuyProduct[] = [];

  if (fs.existsSync(filePath)) {
    const raw = fs.readFileSync(filePath, "utf8");
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        products = parsed;
      } else if (Array.isArray(parsed.products)) {
        products = parsed.products;
      }
    } catch (e) {
      console.error("Erreur parsing BestBuy clearance.json:", e);
    }
  } else {
    console.warn("BestBuy clearance file not found:", filePath);
  }

  return {
    props: {
      products,
    },
    // on pourra ajuster plus tard si tu veux du ISR
    revalidate: 60 * 30, // 30 minutes
  };
};

export default function BestBuyPage({ products }: BestBuyPageProps) {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-4">
          Liquidations Best Buy – EconoDeal
        </h1>
        <p className="mb-6 text-sm text-slate-300">
          Source&nbsp;: <code>outputs/bestbuy/clearance.json</code> –{" "}
          {products.length} produits en liquidation.
        </p>

        {products.length === 0 ? (
          <p className="text-red-400">
            Aucune donnée trouvée. Vérifie que le workflow a bien créé
            <code> outputs/bestbuy/clearance.json</code> dans le repo
            Econo-econo111.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((p, index) => (
              <article
                key={p.sku ?? index}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col"
              >
                {p.imageUrl && (
                  <div className="mb-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={p.imageUrl}
                      alt={p.title ?? "BestBuy product"}
                      className="w-full h-40 object-contain"
                    />
                  </div>
                )}

                <h2 className="font-semibold text-sm mb-1 line-clamp-2">
                  {p.title ?? "Produit BestBuy"}
                </h2>

                <p className="text-xs text-slate-400 mb-1">
                  {p.brand && <span>Marque : {p.brand}</span>}
                  {p.category && (
                    <span className="block">Catégorie : {p.category}</span>
                  )}
                  {p.sku && <span>SKU : {p.sku}</span>}
                </p>

                <div className="mt-auto">
                  <div className="flex items-baseline gap-2 mb-2">
                    {p.currentPrice != null && (
                      <span className="text-lg font-bold text-emerald-400">
                        {p.currentPrice.toFixed(2)} $
                      </span>
                    )}
                    {p.originalPrice != null && (
                      <span className="text-xs line-through text-slate-500">
                        {p.originalPrice.toFixed(2)} $
                      </span>
                    )}
                    {p.discountPercent != null && (
                      <span className="text-xs font-semibold text-rose-400">
                        -{p.discountPercent.toFixed(0)} %
                      </span>
                    )}
                  </div>

                  {p.productUrl && (
                    <a
                      href={p.productUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center justify-center text-xs px-3 py-1.5 rounded-full bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold"
                    >
                      Voir sur Best Buy
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
