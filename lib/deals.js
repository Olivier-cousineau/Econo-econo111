import fs from 'fs';
import path from 'path';

function readJsonIfExists(filePath) {
  if (!fs.existsSync(filePath)) return null;
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    console.error("JSON READ ERROR:", err);
    return null;
  }
}

export default function dealsHandler(req, res) {
  const { retailer, storeSlug } = req.query;

  if (!retailer || !storeSlug) {
    return res.status(400).json({ error: "Missing retailer or storeSlug" });
  }

  const root = process.cwd();

  // ---- Canadian Tire ----
  if (retailer === "canadian-tire") {
    const file = path.join(root, "outputs", "canadiantire", storeSlug, "data.json");
    const data = readJsonIfExists(file);
    if (!data) return res.status(404).json({ error: "Canadian Tire store not found" });
    return res.status(200).json(data);
  }

  // ---- Bureau en Gros ----
  if (retailer === "bureau-en-gros") {
    const file = path.join(root, "outputs", "bureauengros", storeSlug, "data.json");
    const data = readJsonIfExists(file);
    if (!data) return res.status(404).json({ error: "Bureau en Gros store not found" });
    return res.status(200).json(data);
  }

  return res.status(400).json({ error: "Unknown retailer" });
}
