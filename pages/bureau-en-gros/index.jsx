// pages/bureau-en-gros/index.jsx

import Link from 'next/link';
import { getBureauEnGrosStores } from '../../lib/bureauEngros';

export const getStaticProps = async () => {
  const stores = getBureauEnGrosStores().map((store) => ({
    storeSlug: store.slug,
    storeId: store.id,
    city: store.city,
    label: store.name,
    address: store.address,
  }));

  stores.sort((a, b) => a.label.localeCompare(b.label));

  return {
    props: { stores },
    revalidate: 300,
  };
};

const BureauEnGrosIndexPage = ({ stores }) => {
  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '1100px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 700 }}>
          Bureau en Gros – Produits en liquidation
        </h1>
        <p style={{ marginTop: '0.5rem', color: '#4b5563' }}>
          Sélectionne un magasin ci-dessous pour voir sa page. Les liquidations seront
          ajoutées prochainement.
        </p>
      </header>

      {stores.length === 0 ? (
        <p>Aucun magasin Bureau en Gros n’est encore listé.</p>
      ) : (
        <>
          <p style={{ marginBottom: '1rem', color: '#4b5563' }}>
            Bureau en Gros clearance deals are not available yet. They will be added
            soon.
          </p>
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
                <div style={{ fontSize: '0.9rem', color: '#6b7280' }}>
                  Magasin #{store.storeId}
                </div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600 }}>{store.label}</h2>
                {store.address && (
                  <p style={{ fontSize: '0.9rem', color: '#4b5563' }}>
                    {store.address}
                  </p>
                )}
                <Link
                  href={`/bureau-en-gros/${store.storeSlug}`}
                  style={{
                    marginTop: 'auto',
                    fontSize: '0.9rem',
                    color: '#2563eb',
                    fontWeight: 500,
                  }}
                >
                  Voir la page du magasin →
                </Link>
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
};

export default BureauEnGrosIndexPage;
