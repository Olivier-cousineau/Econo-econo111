import { GetStaticPaths, GetStaticProps } from 'next';
import Head from 'next/head';
import { listBureauEnGrosStoreSlugs, readBureauEnGrosDeals } from '../../lib/bureauEngros';

type Deal = {
  name?: string;
  title?: string;
  productName?: string;
  price?: number | string;
  currentPrice?: number | string;
  salePrice?: number | string;
  image?: string;
  imageUrl?: string;
  url?: string;
  link?: string;
  [key: string]: any;
};

type Props = {
  storeSlug: string;
  deals: Deal[];
};

function formatStoreLabel(slug: string): string {
  // Example slug: 124-bureau-en-gros-saint-jerome-qc
  // We just show it as-is for now, or you can prettify it
  return slug.replace(/-/g, ' ');
}

export default function BureauEnGrosStorePage({ storeSlug, deals }: Props) {
  const title = `Liquidations Bureau en Gros – ${formatStoreLabel(storeSlug)}`;
  const count = deals?.length ?? 0;

  return (
    <>
      <Head>
        <title>{title}</title>
      </Head>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-2">{title}</h1>
        <p className="text-sm text-gray-600 mb-6">
          {count} produits en liquidation pour ce magasin.
        </p>

        {count === 0 ? (
          <p>Aucune liquidation trouvée pour ce magasin pour le moment.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {deals.map((deal, index) => {
              const displayName =
                deal.name || deal.title || deal.productName || 'Produit sans nom';
              const price =
                deal.salePrice ?? deal.currentPrice ?? deal.price ?? 'Prix non disponible';
              const image = deal.image || deal.imageUrl;
              const href = deal.url || deal.link || '#';

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
                        alt={displayName}
                        className="object-contain max-h-full"
                      />
                    </div>
                  )}
                  <h2 className="font-semibold text-sm line-clamp-2">{displayName}</h2>
                  <div className="text-sm font-bold">{price}</div>
                  {href !== '#' && (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:underline mt-auto"
                    >
                      Voir sur Bureau en Gros
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
  const slugs = listBureauEnGrosStoreSlugs();

  const paths = slugs.map((storeSlug) => ({
    params: { storeSlug },
  }));

  return {
    paths,
    fallback: 'blocking',
  };
};

export const getStaticProps: GetStaticProps<Props> = async ({ params }) => {
  const storeSlug = params?.storeSlug as string;

  const deals = readBureauEnGrosDeals(storeSlug);

  if (!deals) {
    return {
      notFound: true,
    };
  }

  return {
    props: {
      storeSlug,
      deals,
    },
    revalidate: 300, // 5 minutes
  };
};
