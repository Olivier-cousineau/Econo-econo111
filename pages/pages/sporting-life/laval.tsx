// pages/sporting-life/laval.tsx
import fs from "fs";
import path from "path";
import Image from "next/image";
import Link from "next/link";
import type { GetStaticProps, InferGetStaticPropsType } from "next";

type SportingLifeProduct = {
  title: string;
  productUrl: string;
  currentPrice: number | null;
  originalPrice: number | null;
  discountPercent: number | null;
  imageUrl: string | null;
  [key: string]: any;
};

type SportingLifeLavalPageProps = {
  products: SportingLifeProduct[];
};

export const getStaticProps: GetStaticProps<SportingLifeLavalPageProps> = async () => {
  const filePath = path.join(
    process.cwd(),
    "data",
    "sporting-life",
    "laval.json"
  );

  if (!fs.existsSync(filePath)) {
    console.warn("[Sporting Life] laval.json not found at", filePath);
    return {
      props: {
        products: [],
      },
      revalidate: 3600,
    };
  }

  const raw = fs.readFileSync(filePath, "utf8");
  const parsed = JSON.parse(raw);

  let products: SportingLifeProduct[] = [];

  if (Array.isArray(parsed)) {
    products = parsed as SportingLifeProduct[];
  } else if (parsed && Array.isArray(parsed.products)) {
    products = parsed.products as SportingLifeProduct[];
  } else {
    console.warn("[Sporting Life] Unexpected JSON shape for Laval clearance");
  }

  return {
    props: {
      products,
    },
    revalidate: 3600,
  };
};

function formatPrice(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toFixed(2) + " $";
}

const SportingLifeLavalPage = ({
  products,
}: InferGetStaticPropsType<typeof getStaticProps>) => {
  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <header className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              Sporting Life – Laval – Liquidations
            </h1>
            <p className="text-sm text-slate-600">
              Résultats importés du scraper&nbsp;:{" "}
              <strong>{products.length}</strong> produits en liquidation.
            </p>
          </div>
          <div className="text-xs text-slate-500">
            Données statiques (générées à partir du fichier JSON).
          </div>
        </header>

        {products.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500">
            Aucune liquidation trouvée pour le moment. Vérifie que le fichier{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              data/sporting-life/laval.json
            </code>{" "}
            existe et contient des produits.
          </div>
        ) : (
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((product, index) => {
              const {
                title,
                productUrl,
                currentPrice,
                originalPrice,
                discountPercent,
                imageUrl,
              } = product;

              const discount =
                discountPercent ??
                (originalPrice && currentPrice
                  ? Math.round(
                      ((originalPrice - currentPrice) / originalPrice) * 100
                    )
                  : null);

              return (
                <article
                  key={product.productUrl ?? index}
                  className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
                >
                  <div className="relative h-52 w-full bg-slate-100">
                    {imageUrl ? (
                      imageUrl.startsWith("http") ? (
                        <Image
                          src={imageUrl}
                          alt={title ?? "Produit Sporting Life"}
                          fill
                          className="object-contain"
                        />
                      ) : (
                        <img
                          src={imageUrl}
                          alt={title ?? "Produit Sporting Life"}
                          className="h-full w-full object-contain"
                        />
                      )
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">
                        Aucune image
                      </div>
                    )}

                    {discount != null && discount > 0 && (
                      <div className="absolute left-2 top-2 rounded-full bg-emerald-500 px-2 py-1 text-xs font-semibold text-white">
                        -{discount}%
                      </div>
                    )}
                  </div>

                  <div className="flex flex-1 flex-col p-3">
                    <h2 className="mb-1 line-clamp-2 text-sm font-semibold text-slate-900">
                      {title || "Produit sans titre"}
                    </h2>

                    <div className="mb-2 flex flex-wrap items-baseline gap-2">
                      {currentPrice != null && (
                        <span className="text-base font-bold text-emerald-600">
                          {formatPrice(currentPrice)}
                        </span>
                      )}
                      {originalPrice != null && originalPrice > 0 && (
                        <span className="text-xs text-slate-500 line-through">
                          {formatPrice(originalPrice)}
                        </span>
                      )}
                    </div>

                    <div className="mt-auto flex justify-between gap-2">
                      {productUrl ? (
                        <Link
                          href={productUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex flex-1 items-center justify-center rounded-md bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                        >
                          Voir sur Sporting Life
                        </Link>
                      ) : (
                        <span className="flex-1 text-xs text-slate-400">
                          Lien manquant
                        </span>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
};

export default SportingLifeLavalPage;
