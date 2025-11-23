import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const rawFile = path.resolve(__dirname, "..", "data", "raw", "bureauengros_locations.txt");
const outputDir = path.resolve(__dirname, "..", "data", "bureauengros");
const outputFile = path.join(outputDir, "branches.json");

async function main() {
  const content = await fs.readFile(rawFile, "utf8");
  const lines = content.split(/\r?\n/).filter((line) => line.trim() !== "");

  const stores = [];

  for (const line of lines) {
    const trimmed = line.trim();
    const match = trimmed.match(/^(\d+)\s+(.*)$/);

    if (!match) {
      console.warn(`Skipping malformed line: ${line}`);
      continue;
    }

    const storeId = match[1];
    const fullAddress = match[2].trim();

    if (!fullAddress) {
      console.warn(`Skipping line with missing address: ${line}`);
      continue;
    }

    const parts = fullAddress.split(",").map((part) => part.trim());
    const provinceAndPostal = parts.length >= 1 ? parts[parts.length - 1] : "";
    const city = parts.length >= 2 ? parts[parts.length - 2] : "";

    stores.push({
      id: String(storeId),
      name: city || fullAddress,
      address: fullAddress,
      store: "Bureau en Gros",
      city,
      provinceAndPostal,
    });
  }

  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(outputFile, JSON.stringify(stores, null, 2), "utf8");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
