import { promises as fs } from 'fs';
import path from 'path';

const sourceRoot = path.resolve('./outputs/bureauengros');
const destinationRoot = path.resolve('./public/bureau-en-gros');

async function main() {
  let sourceEntries;
  try {
    sourceEntries = await fs.readdir(sourceRoot, { withFileTypes: true });
  } catch (error) {
    console.error(`Failed to read source directory ${sourceRoot}:`, error);
    process.exit(1);
  }

  for (const entry of sourceEntries) {
    if (!entry.isDirectory()) continue;

    const storeSlug = entry.name;
    const sourceFile = path.join(sourceRoot, storeSlug, 'data.json');

    try {
      await fs.access(sourceFile);
    } catch {
      continue;
    }

    const destinationDir = path.join(destinationRoot, storeSlug);
    const destinationFile = path.join(destinationDir, 'data.json');

    await fs.mkdir(destinationDir, { recursive: true });
    await fs.copyFile(sourceFile, destinationFile);
    console.log(`Copied ${storeSlug} to ${destinationFile}`);
  }
}

main().catch((error) => {
  console.error('Error syncing Bureau en Gros files:', error);
  process.exit(1);
});
