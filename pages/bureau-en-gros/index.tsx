import Link from "next/link";
import { GetStaticProps } from "next";
import {
  getAllBureauEnGrosStores,
  BureauEnGrosStore,
} from "../../lib/bureauEnGrosDeals";

type Props = {
  stores: BureauEnGrosStore[];
};

export const getStaticProps: GetStaticProps<Props> = async () => {
  const stores = getAllBureauEnGrosStores();

  return {
    props: {
      stores,
    },
  };
};

export default function BureauEnGrosIndexPage({ stores }: Props) {
  return (
    <main style={{ padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
      <h1>Bureau en Gros – Liquidations</h1>
      <p>
        Toutes les liquidations chargées depuis{" "}
        <code>outputs/bureauengros/**/data.json</code>.
      </p>

      {stores.length === 0 && (
        <p>Aucun magasin Bureau en Gros trouvé dans outputs/bureauengros.</p>
      )}

      <ul>
        {stores.map((store) => (
          <li key={store.slug} style={{ margin: "0.5rem 0" }}>
            <Link href={`/bureau-en-gros/${store.slug}`}>
              {store.label}{" "}
              <span style={{ opacity: 0.7 }}>
                ({store.productCount} produits)
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
