import fs from 'fs';
import path from 'path';

export function readBureauEnGrosDeals(slug: string) {
  const filePath = path.join(
    process.cwd(),
    'outputs',
    'bureauengros',
    slug,
    'data.json'
  );

  if (!fs.existsSync(filePath)) {
    return { store: null, products: [] };
  }

  const raw = fs.readFileSync(filePath, 'utf8');
  return JSON.parse(raw);
}
