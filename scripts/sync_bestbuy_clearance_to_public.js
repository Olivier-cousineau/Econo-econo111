import { promises as fs } from "fs";
import path from "path";

const SOURCE_PATH = path.resolve("./outputs/bestbuy/clearance.json");
const DESTINATIONS = [
  path.resolve("./public/outputs/bestbuy/clearance.json"),
  path.resolve("./public/bestbuy/clearance.json"),
];

async function ensureDirectory(filePath) {
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });
}

async function main() {
  try {
    await fs.access(SOURCE_PATH);
  } catch {
    console.error(`[BestBuy] Source file not found: ${SOURCE_PATH}`);
    process.exit(1);
  }

  const payload = await fs.readFile(SOURCE_PATH, "utf8");
  await Promise.all(
    DESTINATIONS.map(async (destination) => {
      await ensureDirectory(destination);
      await fs.writeFile(destination, payload);
      console.log(`[BestBuy] Copied clearance.json to ${destination}`);
    })
  );
}

main().catch((error) => {
  console.error("[BestBuy] Failed to sync clearance.json", error);
  process.exit(1);
});
