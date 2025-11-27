// pages/bureau-en-gros/[storeSlug].tsx

import { GetStaticPaths, GetStaticProps } from 'next';
import Head from 'next/head';
import {
  getBureauEnGrosStores,
  listBureauEnGrosStoreSlugs,
} from '../../lib/bureauEngros';

type Deal = {
  [key: string]: any;
};

type Props = {
  storeSlug: string;
  storeName?: string;
  deals: Deal[];
};

function formatStoreLabel(slug: string): string {
  return slug.replace(/-/g, ' ');
}

export default function BureauEnGrosStorePage({
  storeSlug,
  storeName,
  deals,
}: Props) {
  const formattedStore = storeName || formatStoreLabel(storeSlug);
  const title = `Liquidations Bureau en Gros – ${formattedStore}`;
  const count = deals?.length ?? 0;

  return (
    <>
      <Head>
        <title>{title}</title>
      </Head>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-2">{title}</h1>
        <p className="text-sm text-gray-600 mb-6">
          Les liquidations Bureau en Gros ne sont pas encore disponibles ici. Elles
          seront ajoutées prochainement.
        </p>

        {count === 0 ? (
          <p>Bureau en Gros clearance deals are not available yet.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* Future rendering of deals when they are available */}
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
  const store = getBureauEnGrosStores().find((entry) => entry.slug === storeSlug);

  const deals: Deal[] = [];

  return {
    props: {
      storeSlug,
      storeName: store?.name,
      deals,
    },
    revalidate: 300,
  };
};
