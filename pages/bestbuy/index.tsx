// pages/bestbuy/index.tsx
import { GetStaticProps } from "next";
import { Deal, readBestBuyDeals } from "../../lib/bestbuy";

type BestBuyPageProps = {
  products: Deal[];
};

const formatPrice = (value: number | null) => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${value.toFixed(2)} $`;
  }
  return "Prix non disponible";
};

export const getStaticProps: GetStaticProps<BestBuyPageProps> = async () => {
  const products = readBestBuyDeals();

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
          Source&nbsp;: <code>outputs/bestbuy/clearance.json</code> – {products.length}{" "}
          produits en liquidation.
        </p>

        {products.length === 0 ? (
          <p className="text-red-400">
            Aucune donnée trouvée. Vérifie que le workflow a bien créé
            <code> outputs/bestbuy/clearance.json</code> dans le repo
            Econo-econo111.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((p) => (
              <article
                key={p.id}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col"
              >
                <h2 className="font-semibold text-sm mb-2 line-clamp-2">
                  {p.title}
                </h2>

                <div className="mt-auto">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-lg font-bold text-emerald-400">
                      {formatPrice(p.currentPrice)}
                    </span>
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
