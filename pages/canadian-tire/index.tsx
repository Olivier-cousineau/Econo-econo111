import fs from 'fs';
import path from 'path';
import Link from 'next/link';
import { GetStaticProps, InferGetStaticPropsType } from 'next';

interface StoreSummary {
  storeSlug: string;
  storeId: string;
  city: string;
  productCount: number;
  label: string;
}

const slugToLabel = (slug: string) => {
  const [storeIdFromSlug, ...citySegments] = slug.split('-');
  const citySlug = citySegments.join('-');
  const cityLabel = citySlug ? citySlug.replace(/-/g, ' ') : 'Unknown';
  const storeId = storeIdFromSlug ?? slug;
  return {
    storeId,
    city: cityLabel,
    label: `${storeId} – ${cityLabel}`,
  };
};

export const getStaticProps: GetStaticProps<{
  stores: StoreSummary[];
}> = async () => {
  const outputsRoot = path.join(process.cwd(), 'outputs', 'canadiantire');
  let dirEntries: fs.Dirent[] = [];

  try {
    dirEntries = await fs.promises.readdir(outputsRoot, { withFileTypes: true });
  } catch (error) {
    console.error('Unable to read outputs/canadiantire directory', error);
    return {
      props: { stores: [] },
      revalidate: 300,
    };
  }

  const stores: StoreSummary[] = [];

  for (const entry of dirEntries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const dataPath = path.join(outputsRoot, entry.name, 'data.json');
    if (!fs.existsSync(dataPath)) {
      continue;
    }

    try {
      const fileContents = await fs.promises.readFile(dataPath, 'utf-8');
      const parsed = JSON.parse(fileContents);
      const products = Array.isArray(parsed) ? parsed : [];
      if (products.length === 0) {
        continue;
      }

      const { storeId, city, label } = slugToLabel(entry.name);
      stores.push({
        storeSlug: entry.name,
        storeId,
        city,
        label,
        productCount: products.length,
      });
    } catch (error) {
      console.warn(`Skipping ${entry.name} because data.json is invalid or unreadable`, error);
      continue;
    }
  }

  stores.sort((a, b) => a.label.localeCompare(b.label));

  return {
    props: { stores },
    revalidate: 300,
  };
};

const CanadianTireIndexPage = ({
  stores,
}: InferGetStaticPropsType<typeof getStaticProps>) => {
  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '1100px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 700 }}>Canadian Tire Liquidation Stores</h1>
        <p style={{ marginTop: '0.5rem', color: '#4b5563' }}>
          Select a store below to view liquidation products available at that specific location.
          Product details only load when you open a store page, keeping this list fast and light.
        </p>
      </header>

      {stores.length === 0 ? (
        <p>No stores were found in the scraper outputs yet.</p>
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
              <h2 style={{ fontSize: '1.2rem', fontWeight: 600 }}>{store.city}</h2>
              <div style={{ fontSize: '0.95rem', color: '#1f2937' }}>
                {store.productCount.toLocaleString()} liquidation products
              </div>
              <Link
                href={`/canadian-tire/${store.storeSlug}`}
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

export default CanadianTireIndexPage;
