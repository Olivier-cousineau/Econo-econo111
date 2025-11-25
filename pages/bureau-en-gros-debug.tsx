import fs from "fs";
import path from "path";
import { GetStaticProps } from "next";

type Props = {
  dirExists: boolean;
  storeFolders: string[];
  sampleFilePath: string | null;
  sampleRaw: string | null;
  error?: string | null;
};

export const getStaticProps: GetStaticProps<Props> = async () => {
  const rootDir = process.cwd();
  const baseDir = path.join(rootDir, "outputs", "bureauengros");

  let dirExists = false;
  let storeFolders: string[] = [];
  let sampleFilePath: string | null = null;
  let sampleRaw: string | null = null;
  let error: string | null = null;

  try {
    dirExists = fs.existsSync(baseDir);
    if (!dirExists) {
      error = `Directory not found: ${baseDir}`;
    } else {
      const entries = fs.readdirSync(baseDir, { withFileTypes: true });
      storeFolders = entries
        .filter((e) => e.isDirectory())
        .map((e) => e.name)
        .sort();

      if (storeFolders.length > 0) {
        const firstSlug = storeFolders[0];
        const jsonPath = path.join(baseDir, firstSlug, "data.json");
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
  } catch (err: any) {
    error = String(err?.message ?? err);
  }

  return {
    props: {
      dirExists,
      storeFolders,
      sampleFilePath,
      sampleRaw,
      error,
    },
  };
};

export default function BureauEnGrosDebugPage(props: Props) {
  return (
    <main style={{ padding: "2rem", maxWidth: 1000, margin: "0 auto" }}>
      <h1>DEBUG – Bureau en Gros outputs</h1>

      <p>
        <strong>Directory exists:</strong> {String(props.dirExists)}
      </p>

      <p>
        <strong>Store folders found:</strong>{" "}
        {props.storeFolders.length} folder(s)
      </p>

      {props.storeFolders.length > 0 && (
        <ul>
          {props.storeFolders.map((slug) => (
            <li key={slug}>{slug}</li>
          ))}
        </ul>
      )}

      <p>
        <strong>Sample data.json path:</strong>{" "}
        {props.sampleFilePath ?? "none"}
      </p>

      {props.error && (
        <p style={{ color: "red" }}>
          <strong>Error:</strong> {props.error}
        </p>
      )}

      <h2>Sample data.json raw content</h2>
      {props.sampleRaw ? (
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
          {props.sampleRaw}
        </pre>
      ) : (
        <p>No sampleRaw content loaded.</p>
      )}
    </main>
  );
}
