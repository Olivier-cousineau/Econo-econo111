import fs from 'fs';
import path from 'path';

export interface CanadianTireStats {
  totalProducts: number;
  totalStores: number;
  updatedAt: string | null;
}

const defaultStats: CanadianTireStats = {
  totalProducts: 0,
  totalStores: 0,
  updatedAt: null,
};

const statsPath = path.join(process.cwd(), 'outputs', 'canadiantire', 'index', 'stats.json');

export async function readCanadianTireStats(): Promise<CanadianTireStats> {
  try {
    const raw = await fs.promises.readFile(statsPath, 'utf-8');
    const parsed = JSON.parse(raw);
    return {
      totalProducts: Number(parsed.totalProducts) || 0,
      totalStores: Number(parsed.totalStores) || 0,
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : null,
    };
  } catch (error) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn('Canadian Tire stats unavailable, falling back to defaults.', error);
    }
    return { ...defaultStats };
  }
}

export function getCanadianTireStatsPath() {
  return statsPath;
}
