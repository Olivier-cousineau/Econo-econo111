import { GetStaticPaths, GetStaticProps } from "next";
import Head from "next/head";
import {
  getBureauEnGrosStores,
  getBureauEnGrosStoreBySlug,
  readBureauEnGrosDealsForStore,
  BureauEnGrosDeal,
} from "../../lib/bureauEngros";

type Props = {
  storeSlug: string;
  storeName: string;
  address?: string;
  deals: BureauEnGrosDeal[];
};

function formatPrice(value: unknown): string {
  if (typeof value === "number") {
    return `${value.toFixed(2)} $`;
  }
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  return "Prix non disponible";
}

export default function BureauEnGrosStorePage({
  storeSlug,
  storeName,
  address,
  deals,
}: Props) {
  const count = deals?.length ?? 0;
  const title = `Liquidations Bureau en Gros – ${storeName}`;

  return (
    <>
      <Head>
        <title>{title}</title>
      </Head>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-1">{title}</h1>
        {address && (
          <p className="text-sm text-gray-500 mb-1">
            Adresse : <span>{address}</span>
          </p>
        )}
        <p className="text-sm text-gray-600 mb-6">
          {count} produit(s) en liquidation pour ce magasin.
        </p>

        {count === 0 ? (
          <p>Aucune liquidation trouvée pour le moment.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {deals.map((deal, index) => {
              const name =
                deal.title || deal.name || deal.productName || "Produit sans nom";

              const image = (deal as any).imageUrl || (deal as any).image;
              const href = deal.productUrl || (deal as any).url || (deal as any).link || "#";

              const currentPrice = formatPrice(deal.currentPrice);
              const originalPrice = formatPrice(deal.originalPrice);
              const discount =
                typeof deal.discountPercent === "number"
                  ? `${deal.discountPercent}%`
                  : null;

              return (
                <article
                  key={index}
                  className="border rounded-lg p-3 flex flex-col gap-2 bg-white shadow-sm"
                >
                  {image && (
                    <div className="w-full h-40 bg-gray-100 flex items-center justify-center overflow-hidden rounded">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={image}
                        alt={name}
                        className="object-contain max-h-full"
                      />
                    </div>
                  )}

                  <h2 className="font-semibold text-sm line-clamp-2">{name}</h2>

                  <div className="text-sm">
                    <div className="font-semibold">{currentPrice}</div>
                    <div className="text-gray-500 line-through text-xs">
                      {originalPrice}
                    </div>
                    {discount && (
                      <div className="text-xs text-green-600 font-semibold">
                        -{discount}
                      </div>
                    )}
                  </div>

                  {href !== "#" && (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-auto text-xs text-blue-600 hover:underline"
                    >
                      Voir le produit sur Bureau en Gros
                    </a>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}

export const getStaticPaths: GetStaticPaths = async () => {
  const stores = getBureauEnGrosStores();

  const paths = stores.map((store) => ({
    params: { storeSlug: store.slug },
  }));

  return {
    paths,
    fallback: "blocking",
  };
};

export const getStaticProps: GetStaticProps<Props> = async ({ params }) => {
  const storeSlug = params?.storeSlug as string;
  const store = getBureauEnGrosStoreBySlug(storeSlug);

  if (!store) {
    return { notFound: true };
  }

  const deals = readBureauEnGrosDealsForStore(storeSlug);

  return {
    props: {
      storeSlug,
      storeName: store.name,
      address: store.address,
      deals,
    },
    revalidate: 300,
  };
};
