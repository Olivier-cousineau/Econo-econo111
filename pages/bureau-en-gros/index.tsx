import fs from 'fs';
import path from 'path';
import Link from 'next/link';
import type { GetStaticProps, InferGetStaticPropsType } from 'next';
import type { BureauEnGrosStoreData, BureauEnGrosStoreInfo } from '../../lib/bureauEnGrosDeals';

interface StoreSummary {
  storeSlug: string;
  storeId: string;
  label: string;
  city: string;
  productCount: number;
  dataPath: string;
}

const outputsRoot = path.join(process.cwd(), 'outputs', 'bureauengros');

const slugToCity = (slug: string) => {
  const [, ...rest] = slug.split('-');
  const citySlug = rest.join('-');
  return citySlug ? citySlug.replace(/-/g, ' ') : 'Unknown';
};

const buildStoreSummary = (slug: string, data: BureauEnGrosStoreData): StoreSummary | null => {
  const storeInfo: BureauEnGrosStoreInfo | null = (data.store as BureauEnGrosStoreInfo) ?? null;
  const storeName = storeInfo?.name?.trim();
  const { storeId, city } = (() => {
    if (storeInfo?.id) {
      return { storeId: String(storeInfo.id).trim(), city: slugToCity(slug) };
    }
    const [firstSegment, ...rest] = slug.split('-');
    return { storeId: firstSegment ?? slug, city: rest.join('-').replace(/-/g, ' ') };
  })();

  const cityLabelFromName = storeName?.includes('–') ? storeName.split('–')[1]?.trim() : undefined;
  const cityLabel = cityLabelFromName || city || 'Unknown';
  const label = storeName || `Bureau en Gros – ${cityLabel}`;

  const productCount = Array.isArray(data.products) ? data.products.length : 0;
  if (productCount === 0) return null;

  const dataPath = path.posix.join('outputs', 'bureauengros', slug, 'data.json');

  return {
    storeSlug: slug,
    storeId,
    label,
    city: cityLabel,
    productCount,
    dataPath,
  };
};

export const getStaticProps: GetStaticProps<{ stores: StoreSummary[] }> = async () => {
  let dirEntries: fs.Dirent[] = [];

  try {
    dirEntries = await fs.promises.readdir(outputsRoot, { withFileTypes: true });
  } catch (error) {
    console.error('Unable to read outputs/bureauengros directory', error);
    return { props: { stores: [] }, revalidate: 300 };
  }

  const stores: StoreSummary[] = [];

  for (const entry of dirEntries) {
    if (!entry.isDirectory()) continue;

    const dataPath = path.join(outputsRoot, entry.name, 'data.json');
    if (!fs.existsSync(dataPath)) continue;

    try {
      const raw = await fs.promises.readFile(dataPath, 'utf-8');
      const parsed = JSON.parse(raw) as BureauEnGrosStoreData;
      const summary = buildStoreSummary(entry.name, parsed);
      if (summary) {
        stores.push(summary);
      }
    } catch (error) {
      console.warn(`Skipping ${entry.name} because data.json is invalid or unreadable`, error);
    }
  }

  stores.sort((a, b) => a.label.localeCompare(b.label));

  return {
    props: { stores },
    revalidate: 300,
  };
};

const BureauEnGrosIndexPage = ({ stores }: InferGetStaticPropsType<typeof getStaticProps>) => {
  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '1100px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 700 }}>Bureau en Gros Clearance Stores</h1>
        <p style={{ marginTop: '0.5rem', color: '#4b5563' }}>
          Select a store below to view clearance products directly from the scraper outputs. Every entry comes
          from <code>outputs/bureauengros/&lt;store&gt;/data.json</code>.
        </p>
      </header>

      {stores.length === 0 ? (
        <p>No Bureau en Gros stores were found in the scraper outputs yet.</p>
      ) : (
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '1.25rem',
          }}
        >
          {stores.map((store) => (
            <article
              key={store.storeSlug}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: '0.75rem',
                padding: '1.25rem',
                background: '#fff',
                boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
              }}
            >
              <div style={{ fontSize: '0.9rem', color: '#6b7280' }}>Store #{store.storeId}</div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 600 }}>{store.label}</h2>
              <div style={{ fontSize: '0.95rem', color: '#1f2937' }}>
                {store.productCount.toLocaleString()} clearance products
              </div>
              <div style={{ fontSize: '0.85rem', color: '#6b7280', wordBreak: 'break-all' }}>{store.dataPath}</div>
              <Link
                href={`/bureau-en-gros/${store.storeSlug}`}
                style={{
                  marginTop: 'auto',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0.65rem 1rem',
                  borderRadius: '999px',
                  backgroundColor: '#2563eb',
                  color: '#fff',
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                View products
              </Link>
            </article>
          ))}
        </section>
      )}
    </main>
  );
};

export default BureauEnGrosIndexPage;
