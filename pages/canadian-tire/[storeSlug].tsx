import fs from 'fs';
import path from 'path';
import Link from 'next/link';
import { GetStaticPaths, GetStaticProps, InferGetStaticPropsType } from 'next';
import { useMemo, useState } from 'react';

interface RawProduct {
  title?: string;
  sku?: string;
  product_sku?: string;
  product_id?: string | number | null;
  url?: string;
  image?: string;
  price?: number;
  sale_price?: number | null;
  regular_price?: number | null;
  price_raw?: string;
  sale_price_raw?: string | null;
  regular_price_raw?: string | null;
  liquidation?: boolean;
  liquidation_price?: number | null;
  liquidation_price_raw?: string | null;
  availability?: string | null;
  store_id?: string;
  city?: string;
  [key: string]: unknown;
}

interface StoreProduct extends RawProduct {
  storeId: string;
  city: string;
  storeSlug: string;
}

const PAGE_SIZE = 48;

const slugToLabel = (slug: string) => {
  const [storeIdFromSlug, ...citySegments] = slug.split('-');
  const citySlug = citySegments.join('-');
  const cityLabel = citySlug ? citySlug.replace(/-/g, ' ') : 'Unknown';
  const storeId = storeIdFromSlug ?? slug;
  return { storeId, city: cityLabel };
};

export const getStaticPaths: GetStaticPaths = async () => {
  const outputsRoot = path.join(process.cwd(), 'outputs', 'canadiantire');
  let dirEntries: fs.Dirent[] = [];

  try {
    dirEntries = await fs.promises.readdir(outputsRoot, { withFileTypes: true });
  } catch (error) {
    console.error('Unable to read outputs/canadiantire directory for paths', error);
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
  products: StoreProduct[];
  storeId: string;
  city: string;
  storeSlug: string;
}> = async ({ params }) => {
  const storeSlug = typeof params?.storeSlug === 'string' ? params.storeSlug : '';
  if (!storeSlug) {
    return { notFound: true };
  }

  const dataPath = path.join(process.cwd(), 'outputs', 'canadiantire', storeSlug, 'data.json');
  if (!fs.existsSync(dataPath)) {
    return { notFound: true };
  }

  let fileContents: string;
  try {
    fileContents = await fs.promises.readFile(dataPath, 'utf-8');
  } catch (error) {
    console.error(`Unable to read data for store ${storeSlug}`, error);
    return { notFound: true };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(fileContents);
  } catch (error) {
    console.error(`Invalid JSON for store ${storeSlug}`, error);
    return { notFound: true };
  }

  const rawProducts: RawProduct[] = Array.isArray(parsed) ? parsed : [];
  if (rawProducts.length === 0) {
    return { notFound: true };
  }

  const { storeId, city } = slugToLabel(storeSlug);
  const products: StoreProduct[] = rawProducts.map((product, index) => ({
    ...product,
    storeId: String(product.store_id ?? storeId),
    city: String(product.city ?? city),
    storeSlug,
    sku: product.sku ?? product.product_sku ?? `${storeSlug}-${index}`,
  }));

  return {
    props: {
      products,
      storeId,
      city,
      storeSlug,
    },
    revalidate: 300,
  };
};

const formatCurrency = (value?: number | null, fallbackRaw?: string | null) => {
  if (typeof value === 'number') {
    return new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(value);
  }
  if (fallbackRaw) {
    return fallbackRaw;
  }
  return 'N/A';
};

const computeDiscount = (product: RawProduct) => {
  const regular = product.regular_price ?? product.price ?? null;
  const liquidation = product.liquidation_price ?? product.sale_price ?? null;
  if (typeof regular === 'number' && typeof liquidation === 'number' && regular > 0) {
    const percent = Math.round(((regular - liquidation) / regular) * 100);
    return Math.max(percent, 0);
  }
  return null;
};

const StorePage = ({
  products,
  storeId,
  city,
  storeSlug,
}: InferGetStaticPropsType<typeof getStaticProps>) => {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(products.length / PAGE_SIZE));

  const visibleProducts = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return products.slice(start, start + PAGE_SIZE);
  }, [page, products]);

  const handlePrev = () => setPage((prev) => Math.max(1, prev - 1));
  const handleNext = () => setPage((prev) => Math.min(totalPages, prev + 1));

  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <p style={{ marginBottom: '0.5rem' }}>
          <Link href="/canadian-tire" style={{ color: '#2563eb' }}>
            ← Back to store list
          </Link>
        </p>
        <h1 style={{ fontSize: '2rem', fontWeight: 700 }}>Store #{storeId} – {city}</h1>
        <p style={{ color: '#4b5563' }}>
          Showing {products.length.toLocaleString()} liquidation products from slug "{storeSlug}".
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
        {visibleProducts.map((product, index) => {
          const discount = computeDiscount(product);
          return (
            <article
              key={`${product.storeSlug}-${product.sku ?? product.product_sku ?? index}`}
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
              <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>{product.title ?? 'Untitled product'}</h2>
              {product.image && (
                <img
                  src={product.image}
                  alt={product.title ?? ''}
                  style={{ width: '100%', height: '180px', objectFit: 'contain' }}
                  loading="lazy"
                />
              )}
              <div style={{ fontSize: '1rem', fontWeight: 600 }}>
                Liquidation: {formatCurrency(product.liquidation_price ?? product.sale_price ?? null, product.liquidation_price_raw ?? product.sale_price_raw)}
              </div>
              <div style={{ fontSize: '0.95rem', color: '#4b5563' }}>
                Regular: {formatCurrency(product.regular_price ?? product.price ?? null, product.regular_price_raw ?? product.price_raw)}
              </div>
              {typeof discount === 'number' && (
                <div style={{ color: '#059669', fontWeight: 600 }}>{discount}% off</div>
              )}
              {product.availability && (
                <div style={{ fontSize: '0.85rem', color: '#6b7280' }}>{product.availability}</div>
              )}
              {product.url && (
                <a
                  href={product.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#2563eb', textDecoration: 'underline', fontWeight: 500 }}
                >
                  View product
                </a>
              )}
            </article>
          );
        })}
      </section>
    </main>
  );
};

export default StorePage;
