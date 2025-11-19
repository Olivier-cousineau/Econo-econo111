import React from 'react';
import type { CanadianTireStats } from '../lib/canadianTireStats';

interface CanadianTireStatsCardProps {
  stats: CanadianTireStats;
}

const formatNumber = (value: number | undefined) =>
  new Intl.NumberFormat('fr-CA').format(Number.isFinite(value ?? 0) ? Number(value) : 0);

export const CanadianTireStatsCard: React.FC<CanadianTireStatsCardProps> = ({ stats }) => {
  const totalProductsLabel = formatNumber(stats.totalProducts ?? 0);
  const totalStoresLabel = formatNumber(stats.totalStores ?? 0);

  return (
    <section
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: '1rem',
        background: '#f9fafb',
        padding: '1.25rem',
        marginBottom: '1.5rem',
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
        fontSize: '1rem',
        color: '#111827',
        lineHeight: 1.6,
      }}
    >
      <p style={{ margin: 0 }}>
        ✅ EconoDeal suit actuellement <strong>{totalProductsLabel}</strong> liquidations Canadian Tire dans{' '}
        <strong>{totalStoresLabel}</strong> magasins au Canada.
      </p>
    </section>
  );
};

export default CanadianTireStatsCard;
