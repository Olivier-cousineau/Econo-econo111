// pages/bestbuy/index.tsx
import { useEffect, useState } from "react";
import { GetStaticProps } from "next";
import Link from "next/link";
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

export default function BestBuyPage({ products: initialProducts }: BestBuyPageProps) {
  const [products, setProducts] = useState<Deal[]>(initialProducts ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    const fetchLatestDeals = async () => {
      try {
        setIsLoading(true);
        const response = await fetch("/api/bestbuy/clearance");

        if (!response.ok) {
          throw new Error("Impossible de récupérer les liquidations Best Buy");
        }

        const payload = await response.json();

        if (isMounted && Array.isArray(payload.deals)) {
          setProducts(payload.deals);
        }
      } catch (err) {
        if (isMounted) {
          setError(
            "Une erreur est survenue lors du chargement des offres de liquidation Best Buy."
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchLatestDeals();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-4">
          Liquidations Best Buy – EconoDeal
        </h1>
        <p className="mb-4 text-sm text-slate-300">
          Source&nbsp;: <code>outputs/bestbuy/clearance.json</code> – {products.length}{" "}
          produits en liquidation en ligne.
        </p>
        <div className="flex items-center gap-4 text-sm mb-6">
          {isLoading && <span className="text-emerald-300">Mise à jour…</span>}
          {error && <span className="text-red-400">{error}</span>}
          <Link href="/" className="text-emerald-300 hover:text-emerald-200">
            ← Retour à l’accueil
          </Link>
        </div>

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
