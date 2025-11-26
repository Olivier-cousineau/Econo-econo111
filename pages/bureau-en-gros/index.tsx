import fs from "fs";
import path from "path";

import type { GetStaticProps } from "next";

import Link from "next/link";

import type { Product } from "./types";

// Shared product type for this directory
export type { Product } from "./types";

interface Props {
  products: Product[];
}

export const getStaticProps: GetStaticProps<Props> = async () => {
  const filePath = path.join(
    process.cwd(),
    "outputs",
    "bureauengros",
    "clearance",
    "data.json"
  );

  let products: Product[] = [];

  if (fs.existsSync(filePath)) {
    const raw = fs.readFileSync(filePath, "utf8");
    try {
      const parsed = JSON.parse(raw);
      // Accept either an array or an object with a "products" field
      products = Array.isArray(parsed) ? parsed : parsed.products || [];
    } catch (error) {
      console.error("Failed to parse Bureau en Gros clearance JSON:", error);
      products = [];
    }
  } else {
    console.warn("Bureau en Gros clearance file not found:", filePath);
  }

  return {
    props: {
      products,
    },
    revalidate: 300,
  };
};

export default function BureauEnGrosClearancePage({ products }: Props) {
  return (
    <main className="container mx-auto px-4 py-8">
      <header className="flex items-center justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold mb-2">Bureau en Gros – Clearance deals</h1>
          <p>
            {products.length} clearance products currently available across Bureau en Gros
            stores.
          </p>
        </div>
        <Link
          href="/"
          className="text-blue-600 hover:text-blue-800 underline"
        >
          ← Back home
        </Link>
      </header>

      {products.length === 0 ? (
        <p>No clearance products were found. Please try again later.</p>
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
              {product.storeName && (
                <p className="text-sm text-gray-600 mb-1">{product.storeName}</p>
              )}
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
