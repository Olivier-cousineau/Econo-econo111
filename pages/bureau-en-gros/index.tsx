// pages/bureau-en-gros/index.tsx
import { GetStaticProps } from "next";
import Head from "next/head";
import Link from "next/link";
import {
  listAvailableBureauEnGrosStoreSlugs,
  readBureauEnGrosStoreData,
} from "../../lib/server/bureauEnGrosData";

type StoreSummary = {
  storeSlug: string;
  storeId: number | null;
  storeName: string | null;
  city: string | null;
  province: string | null;
  count: number;
};

type BureauEnGrosIndexProps = {
  stores: StoreSummary[];
};

function slugToLabel(slug: string) {
  // ex: "124-bureau-en-gros-saint-jerome-qc"
  const parts = slug.split("-");
  const storeId = parts[0] ?? slug;
  const cityParts = parts.slice(4, -1); // ["saint", "jerome"]
  const province = parts[parts.length - 1] ?? null;

  const city =
    cityParts.length > 0
      ? cityParts.join(" ").replace(/\b\w/g, (c) => c.toUpperCase())
      : null;

  return {
    storeId,
    city,
    province: province ? province.toUpperCase() : null,
  };
}

export const getStaticProps: GetStaticProps<BureauEnGrosIndexProps> = async () => {
  let stores: StoreSummary[] = [];

  try {
    const slugs = listAvailableBureauEnGrosStoreSlugs();

    stores = slugs
      .map((slug) => {
        try {
          const data = readBureauEnGrosStoreData(slug);
          if (!data) return null;

          const products = Array.isArray(data.products) ? data.products : [];
          const count =
            typeof data.count === "number" ? data.count : products.length;

          const label = slugToLabel(slug);

          return {
            storeSlug: slug,
            storeId: (data as any).storeId ?? (data as any).store?.id ?? null,
            storeName:
              (data as any).storeName ??
              (data as any).store?.name ??
              `Bureau en Gros ${label.city ?? ""}`,
            city: label.city,
            province: label.province,
            count,
          } as StoreSummary;
        } catch (err) {
          console.error("Error reading Bureau en Gros data for slug:", slug, err);
          return null;
        }
      })
      .filter((s): s is StoreSummary => Boolean(s));
  } catch (err) {
    console.error("Failed to list Bureau en Gros stores:", err);
    stores = [];
  }

  return {
    props: {
      stores,
    },
    revalidate: 300, // regen toutes les 5 minutes
  };
};

export default function BureauEnGrosIndex({ stores }: BureauEnGrosIndexProps) {
  return (
    <>
      <Head>
        <title>Bureau en Gros – Liquidations par magasin | EconoDeal</title>
      </Head>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-4">
          Liquidations Bureau en Gros par magasin
        </h1>

        {stores.length === 0 && (
          <p>
            Aucune donnée n&apos;est disponible actuellement pour Bureau en Gros.
            Essayez de revenir plus tard, le scraper est peut-être en cours
            d&apos;exécution.
          </p>
        )}

        {stores.length > 0 && (
          <ul className="space-y-2">
            {stores.map((store) => (
              <li
                key={store.storeSlug}
                className="border rounded-md px-4 py-3 flex justify-between items-center"
              >
                <div>
                  <div className="font-semibold">
                    {store.storeName}{" "}
                    {store.city && `– ${store.city}`}
                    {store.province && ` (${store.province})`}
                  </div>
                  <div className="text-sm text-gray-600">
                    ID magasin: {store.storeId ?? store.storeSlug} ·{" "}
                    {store.count} liquidation(s)
                  </div>
                </div>
                <Link
                  href={`/bureau-en-gros/${store.storeSlug}`}
                  className="text-blue-600 underline text-sm"
                >
                  Voir les liquidations
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
