import fs from "fs";
import path from "path";

const OUTPUT_DIR = path.join(process.cwd(), "outputs", "bureauengros");

async function loadDebugInfo() {
  let dirExists = false;
  let storeFolders = [];
  let sampleFilePath = null;
  let sampleRaw = null;
  let error = null;

  try {
    dirExists = fs.existsSync(OUTPUT_DIR);

    if (!dirExists) {
      error = `Directory not found: ${OUTPUT_DIR}`;
    } else {
      const entries = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true });
      storeFolders = entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => entry.name)
        .sort();

      if (storeFolders.length > 0) {
        const firstSlug = storeFolders[0];
        const jsonPath = path.join(OUTPUT_DIR, firstSlug, "data.json");
        sampleFilePath = jsonPath;

        if (fs.existsSync(jsonPath)) {
          sampleRaw = fs.readFileSync(jsonPath, "utf8");
        } else {
          error = `data.json not found for first store: ${jsonPath}`;
        }
      } else {
        error = "No subfolders found under outputs/bureauengros.";
      }
    }
  } catch (err) {
    error = String(err?.message ?? err);
  }

  return { dirExists, storeFolders, sampleFilePath, sampleRaw, error };
}

export default async function BureauEnGrosDebugPage() {
  const info = await loadDebugInfo();

  return (
    <main style={{ padding: "2rem", maxWidth: 1000, margin: "0 auto" }}>
      <h1>DEBUG – Bureau en Gros outputs</h1>

      <p>
        <strong>Directory exists:</strong> {String(info.dirExists)}
      </p>

      <p>
        <strong>Store folders found:</strong> {info.storeFolders.length} folder(s)
      </p>

      {info.storeFolders.length > 0 && (
        <ul>
          {info.storeFolders.map((slug) => (
            <li key={slug}>{slug}</li>
          ))}
        </ul>
      )}

      <p>
        <strong>Sample data.json path:</strong> {info.sampleFilePath ?? "none"}
      </p>

      {info.error && (
        <p style={{ color: "red" }}>
          <strong>Error:</strong> {info.error}
        </p>
      )}

      <h2>Sample data.json raw content</h2>
      {info.sampleRaw ? (
        <pre
          style={{
            maxHeight: "400px",
            overflow: "auto",
            background: "#111",
            color: "#0f0",
            padding: "1rem",
            borderRadius: 8,
            fontSize: "0.8rem",
          }}
        >
          {info.sampleRaw}
        </pre>
      ) : (
        <p>No sampleRaw content loaded.</p>
      )}
    </main>
  );
}
