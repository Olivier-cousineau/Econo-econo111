import fs from 'fs';
import path from 'path';
import Link from 'next/link';
import type { GetStaticPaths, GetStaticProps, InferGetStaticPropsType } from 'next';
import { useMemo, useState } from 'react';
import type { BureauEnGrosProduct, BureauEnGrosStoreData, BureauEnGrosStoreInfo } from '../../lib/bureauEnGrosDeals';
import { readBureauEnGrosStoreDeals } from '../../lib/bureauEnGrosDeals';

interface DealView {
  retailer: 'bureauengros';
  title: string;
  url: string;
  price: number | null;
  originalPrice: number | null;
  discountPercent: number | null;
  image: string | null;
  availability: string | null;
}

interface StoreMeta {
  storeId: string;
  city: string;
  storeName: string;
  storeSlug: string;
}

const PAGE_SIZE = 48;
const outputsRoot = path.join(process.cwd(), 'outputs', 'bureauengros');

const pickNumber = (...values: unknown[]): number | null => {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
};

const computeDiscount = (price: number | null, original: number | null, provided?: unknown) => {
  if (typeof provided === 'number' && Number.isFinite(provided)) {
    return Math.round(provided);
  }
  if (price !== null && original !== null && original > 0) {
    return Math.max(Math.round(((original - price) / original) * 100), 0);
  }
  return null;
};

const normalizeDeal = (product: BureauEnGrosProduct): DealView => {
  const price = pickNumber(
    product.currentPrice,
    product.salePrice,
    product.discountPrice,
    product.discount_price,
    product.price,
    product.regularPrice,
    product.originalPrice,
  );
  const originalPrice = pickNumber(product.originalPrice, product.regularPrice);
  const discountPercent = computeDiscount(price, originalPrice, product.discountPercent);

  return {
    retailer: 'bureauengros',
    title: product.title ?? '',
    url: product.productUrl ?? product.url ?? product.link ?? '',
    price,
    originalPrice,
    discountPercent,
    image: (product.imageUrl ?? product.image_url ?? product.image ?? null) as string | null,
    availability: (product.availability ?? null) as string | null,
  };
};

const deriveMeta = (slug: string, data: BureauEnGrosStoreData): StoreMeta => {
  const info: BureauEnGrosStoreInfo | null = (data.store as BureauEnGrosStoreInfo) ?? null;
  const storeId = String(info?.id ?? slug.split('-')[0] ?? slug);
  const storeName = info?.name?.trim() || 'Bureau en Gros';
  const city = (() => {
    const fromName = storeName.includes('–') ? storeName.split('–')[1]?.trim() : '';
    if (fromName) return fromName;
    const [, ...rest] = slug.split('-');
    return rest.join('-').replace(/-/g, ' ') || storeName;
  })();

  return {
    storeId,
    city,
    storeName,
    storeSlug: slug,
  };
};

export const getStaticPaths: GetStaticPaths = async () => {
  let dirEntries: fs.Dirent[] = [];

  try {
    dirEntries = await fs.promises.readdir(outputsRoot, { withFileTypes: true });
  } catch (error) {
    console.error('Unable to read outputs/bureauengros directory for paths', error);
    return { paths: [], fallback: 'blocking' };
  }

  const paths = dirEntries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({ params: { storeSlug: entry.name } }));

  return {
    paths,
    fallback: 'blocking',
  };
};

export const getStaticProps: GetStaticProps<{
  deals: DealView[];
  meta: StoreMeta;
}> = async ({ params }) => {
  const storeSlug = typeof params?.storeSlug === 'string' ? params.storeSlug : '';
  if (!storeSlug) {
    return { notFound: true };
  }

  const data = await readBureauEnGrosStoreDeals(storeSlug);
  if (!data || !Array.isArray(data.products) || data.products.length === 0) {
    return { notFound: true };
  }

  const meta = deriveMeta(storeSlug, data);
  const deals = data.products.map((product) => normalizeDeal(product));

  return {
    props: {
      deals,
      meta,
    },
    revalidate: 300,
  };
};

const BureauEnGrosStorePage = ({ deals, meta }: InferGetStaticPropsType<typeof getStaticProps>) => {
  const [page, setPage] = useState(1);

  const allDeals = useMemo(() => deals, [deals]);

  const visibleDeals = useMemo(() => {
    const filtered = allDeals.filter((deal) => {
      const hasTitle = Boolean(deal.title?.trim());
      const hasPrice = typeof deal.price === 'number' && Number.isFinite(deal.price);
      return hasTitle && hasPrice;
    });

    if (process.env.NODE_ENV !== 'production') {
      console.log('[DEBUG] Total deals loaded:', allDeals.length);
      console.log('[DEBUG] Bureau en Gros deals:', allDeals.filter((d) => d.retailer === 'bureauengros').length);
      console.log('[DEBUG] Visible deals after filtering:', filtered.length);
    }

    return filtered;
  }, [allDeals]);

  const totalPages = Math.max(1, Math.ceil(visibleDeals.length / PAGE_SIZE));

  const paginatedDeals = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return visibleDeals.slice(start, start + PAGE_SIZE);
  }, [page, visibleDeals]);

  const handlePrev = () => setPage((prev) => Math.max(1, prev - 1));
  const handleNext = () => setPage((prev) => Math.min(totalPages, prev + 1));

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <p style={{ marginBottom: '0.5rem' }}>
          <Link href="/bureau-en-gros" style={{ color: '#2563eb' }}>
            ← Back to store list
          </Link>
        </p>
        <h1 style={{ fontSize: '2rem', fontWeight: 700 }}>
          Store #{meta.storeId} – {meta.city}
        </h1>
        <p style={{ color: '#4b5563' }}>
          Showing {visibleDeals.length.toLocaleString()} clearance products from slug "{meta.storeSlug}".
        </p>
      </header>

      <section
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div>
          Page {page} of {totalPages}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handlePrev}
            disabled={page === 1}
            style={{
              padding: '0.5rem 0.9rem',
              borderRadius: '0.5rem',
              border: '1px solid #d1d5db',
              backgroundColor: page === 1 ? '#f3f4f6' : '#fff',
              cursor: page === 1 ? 'not-allowed' : 'pointer',
            }}
          >
            Previous
          </button>
          <button
            onClick={handleNext}
            disabled={page === totalPages}
            style={{
              padding: '0.5rem 0.9rem',
              borderRadius: '0.5rem',
              border: '1px solid #d1d5db',
              backgroundColor: page === totalPages ? '#f3f4f6' : '#fff',
              cursor: page === totalPages ? 'not-allowed' : 'pointer',
            }}
          >
            Next
          </button>
        </div>
      </section>

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gap: '1rem',
        }}
      >
        {paginatedDeals.map((deal, index) => (
          <article
            key={`${meta.storeSlug}-${deal.title}-${index}`}
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: '0.75rem',
              padding: '1rem',
              background: '#fff',
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>{deal.title || 'Untitled product'}</h2>
            {deal.image && (
              <img
                src={deal.image}
                alt={deal.title ?? ''}
                style={{ width: '100%', height: '180px', objectFit: 'contain' }}
                loading="lazy"
              />
            )}
            <div style={{ fontSize: '1rem', fontWeight: 600 }}>
              Current: {typeof deal.price === 'number' ? `$${deal.price.toFixed(2)}` : 'N/A'}
            </div>
            <div style={{ fontSize: '0.95rem', color: '#4b5563' }}>
              Regular: {typeof deal.originalPrice === 'number' ? `$${deal.originalPrice.toFixed(2)}` : 'N/A'}
            </div>
            {typeof deal.discountPercent === 'number' && (
              <div style={{ color: '#059669', fontWeight: 600 }}>{deal.discountPercent}% off</div>
            )}
            {deal.availability && (
              <div style={{ fontSize: '0.85rem', color: '#6b7280' }}>{deal.availability}</div>
            )}
            {deal.url && (
              <a
                href={deal.url}
                target="_blank"
                rel="noreferrer"
                style={{ color: '#2563eb', textDecoration: 'underline', fontWeight: 500 }}
              >
                View product
              </a>
            )}
          </article>
        ))}
      </section>
    </main>
  );
};

export default BureauEnGrosStorePage;
