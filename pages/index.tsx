import Link from 'next/link';
import type { GetStaticProps, InferGetStaticPropsType } from 'next';
import { CanadianTireStatsCard } from '../components/CanadianTireStatsCard';
import { readCanadianTireStats, type CanadianTireStats } from '../lib/canadianTireStats';

export const getStaticProps: GetStaticProps<{ stats: CanadianTireStats }> = async () => {
  const stats = await readCanadianTireStats();
  return {
    props: { stats },
    revalidate: 300,
  };
};

const HomePage = ({ stats }: InferGetStaticPropsType<typeof getStaticProps>) => {
  return (
    <main style={{ padding: '2rem 1rem', maxWidth: '900px', margin: '0 auto' }}>
      <header style={{ marginBottom: '2rem' }}>
        <p
          style={{
            textTransform: 'uppercase',
            color: '#2563eb',
            fontWeight: 600,
            letterSpacing: '0.05em',
            fontSize: '0.85rem',
          }}
        >
          Transparence des liquidations
        </p>
        <h1 style={{ fontSize: '2.5rem', fontWeight: 700, marginBottom: '0.75rem' }}>
          EconoDeal aide les chasseurs d'aubaines au Canada
        </h1>
        <p style={{ fontSize: '1.15rem', color: '#4b5563', lineHeight: 1.6 }}>
          Nous surveillons en continu les liquidations Canadian Tire pour découvrir les meilleures offres
          disponibles dans chaque magasin. Consultez la carte des magasins pour explorer vos liquidations
          locales en détail.
        </p>
      </header>

      <CanadianTireStatsCard stats={stats} />

      <section style={{ display: 'flex', gap: '1rem' }}>
        <Link
          href="/canadian-tire"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0.85rem 1.5rem',
            borderRadius: '999px',
            backgroundColor: '#2563eb',
            color: '#fff',
            fontWeight: 600,
            textDecoration: 'none',
          }}
        >
          Explorer les magasins Canadian Tire
        </Link>
      </section>
    </main>
  );
};

export default HomePage;
