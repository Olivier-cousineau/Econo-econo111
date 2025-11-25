import fs from "fs";
import path from "path";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  buildBureauEnGrosStore,
  filterVisibleBureauEnGrosDeals,
} from "../../../lib/bureauEnGrosDeals";

const OUTPUT_DIR = path.join(process.cwd(), "outputs", "bureauengros");

function readStoreSlugs() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    return [];
  }

  const entries = fs.readdirSync(OUTPUT_DIR, { withFileTypes: true });
  return entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);
}

export async function generateStaticParams() {
  const slugs = readStoreSlugs();

  return slugs.map((slug) => ({ storeSlug: slug }));
}

function readStoreDeals(storeSlug) {
  const jsonPath = path.join(OUTPUT_DIR, storeSlug, "data.json");

  if (!fs.existsSync(jsonPath)) {
    return { jsonPath, deals: null };
  }

  try {
    const raw = fs.readFileSync(jsonPath, "utf8");
    const parsed = JSON.parse(raw);
    return { jsonPath, deals: Array.isArray(parsed) ? parsed : null };
  } catch (error) {
    console.error("[BureauEnGros] Failed to read data.json for store", storeSlug, jsonPath, error);
    return { jsonPath, deals: null };
  }
}

export default async function BureauEnGrosStorePage({ params }) {
  const slug = params.storeSlug;
  const { jsonPath, deals } = readStoreDeals(slug);

  if (!deals) {
    notFound();
  }

  const visibleDeals = filterVisibleBureauEnGrosDeals(deals);
  const store = buildBureauEnGrosStore(slug, deals.length, jsonPath);

  return (
    <main style={{ padding: "2rem", maxWidth: 1000, margin: "0 auto" }}>
      <p>
        <Link href="/bureau-en-gros">← Retour à la liste des magasins</Link>
      </p>

      <h1>{store.label}</h1>
      <p>
        Fichier : <code>{store.jsonPath}</code>
      </p>
      <p>
        Nombre de produits affichés : <strong>{visibleDeals.length}</strong>
      </p>

      {visibleDeals.length === 0 && (
        <p>
          Aucun produit valide trouvé dans ce fichier. Vérifie que le data.json contient bien un
          tableau d&apos;objets avec au moins <code>title</code> et <code>priceCurrent</code>.
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))",
          gap: "1rem",
          marginTop: "1rem",
        }}
      >
        {visibleDeals.map((deal, idx) => (
          <article
            key={idx}
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: "0.75rem",
            }}
          >
            {deal.imageUrl && (
              <div style={{ textAlign: "center", marginBottom: "0.5rem" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={deal.imageUrl}
                  alt={deal.title ?? ""}
                  style={{ maxWidth: "100%", maxHeight: 160, objectFit: "contain" }}
                />
              </div>
            )}
            <h2 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>
              {deal.title ?? "Sans titre"}
            </h2>
            <p>
              <strong>Prix actuel : </strong>
              {deal.priceCurrent}
            </p>
            {deal.priceOriginal && (
              <p>
                <strong>Prix original : </strong>
                <span style={{ textDecoration: "line-through" }}>{deal.priceOriginal}</span>
              </p>
            )}
            {typeof deal.discountPercent === "number" && (
              <p>
                <strong>Rabais : </strong>
                {deal.discountPercent}%
              </p>
            )}
            {deal.url && (
              <p>
                <a
                  href={deal.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "inline-block",
                    padding: "0.5rem 0.75rem",
                    background: "#2563eb",
                    color: "#fff",
                    borderRadius: 6,
                    textDecoration: "none",
                  }}
                >
                  Voir le produit
                </a>
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
