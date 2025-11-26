import fs from "fs";
import path from "path";

import type { GetStaticPaths, GetStaticProps } from "next";

import Link from "next/link";

import type { Product } from "./types";

interface Props {
  storeSlug: string;
  products: Product[];
}

export const getStaticPaths: GetStaticPaths = async () => {
  const baseDir = path.join(process.cwd(), "outputs", "bureauengros");

  let paths: { params: { storeSlug: string } }[] = [];

  if (fs.existsSync(baseDir)) {
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });

    paths = entries
      .filter(
        (entry) =>
          entry.isDirectory() && entry.name.toLowerCase() !== "clearance"
      )
      .map((entry) => ({
        params: {
          storeSlug: entry.name,
        },
      }));
  } else {
    console.warn("Bureau en Gros output directory not found:", baseDir);
  }

  return {
    paths,
    fallback: false,
  };
};

export const getStaticProps: GetStaticProps<Props> = async ({ params }) => {
  const storeSlug = params?.storeSlug as string;

  const filePath = path.join(
    process.cwd(),
    "outputs",
    "bureauengros",
    storeSlug,
    "data.json"
  );

  let products: Product[] = [];

  if (fs.existsSync(filePath)) {
    const raw = fs.readFileSync(filePath, "utf8");
    try {
      const parsed = JSON.parse(raw);
      products = Array.isArray(parsed) ? parsed : parsed.products || [];
    } catch (error) {
      console.error(
        `Failed to parse Bureau en Gros store JSON for ${storeSlug}:`,
        error
      );
      products = [];
    }
  } else {
    console.warn("Bureau en Gros store file not found:", filePath);
  }

  return {
    props: {
      storeSlug,
      products,
    },
    revalidate: 300,
  };
};

export default function BureauEnGrosStorePage({
  storeSlug,
  products,
}: Props) {
  const titleSlug = storeSlug.replace(/-/g, " ");

  return (
    <main className="container mx-auto px-4 py-8">
      <header className="mb-6">
        <p className="mb-2">
          <Link href="/bureau-en-gros" className="text-blue-600 underline">
            ← Back to Bureau en Gros clearance
          </Link>
        </p>
        <h1 className="text-2xl font-bold mb-2">Bureau en Gros – {titleSlug}</h1>
        <p>{products.length} clearance products for this store.</p>
      </header>

      {products.length === 0 ? (
        <p>No clearance products were found for this store.</p>
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((product, index) => (
            <article
              key={product.id || product.sku || index}
              className="border rounded-lg p-4 flex flex-col"
            >
              {product.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={product.image}
                  alt={product.name || product.title || ""}
                  className="mb-3 h-40 w-full object-contain"
                  loading="lazy"
                />
              )}
              <h2 className="font-semibold mb-1 line-clamp-2">
                {product.name || product.title || "Unnamed product"}
              </h2>
              <div className="mt-auto pt-2">
                <div className="text-sm">
                  {product.regularPrice && (
                    <span className="line-through mr-2">{String(product.regularPrice)}</span>
                  )}
                  {product.clearancePrice && (
                    <span className="font-bold">{String(product.clearancePrice)}</span>
                  )}
                  {!product.clearancePrice && product.price && (
                    <span className="font-bold">{String(product.price)}</span>
                  )}
                </div>
                {product.url && (
                  <a
                    href={product.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-block mt-2 text-sm underline"
                  >
                    View on Bureau en Gros
                  </a>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
