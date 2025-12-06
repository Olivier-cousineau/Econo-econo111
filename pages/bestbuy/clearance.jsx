import Link from "next/link";
import { useEffect, useState } from "react";
import { readBestBuyClearanceDeals } from "../../lib/bestbuyClearance";

export const getStaticProps = async () => {
  const deals = readBestBuyClearanceDeals();

  return {
    props: { deals },
    revalidate: 300,
  };
};

function formatPrice(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `$${value.toFixed(2)}`;
  }
  return "Prix non disponible";
}

const BestBuyClearancePage = ({ deals: initialDeals }) => {
  const [deals, setDeals] = useState(initialDeals ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    const fetchLatestDeals = async () => {
      try {
        setIsLoading(true);
        const response = await fetch("/api/bestbuy/clearance");

        if (!response.ok) {
          throw new Error("Impossible de récupérer les données de liquidation");
        }

        const payload = await response.json();

        if (isMounted && Array.isArray(payload.deals)) {
          setDeals(payload.deals);
        }
      } catch (err) {
        if (isMounted) {
          setError(
            "Une erreur est survenue lors du chargement des offres de liquidation."
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchLatestDeals();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main style={{ padding: "2rem 1rem", maxWidth: "1100px", margin: "0 auto" }}>
      <header style={{ marginBottom: "2rem" }}>
        <p
          style={{
            textTransform: "uppercase",
            color: "#2563eb",
            fontWeight: 600,
            letterSpacing: "0.05em",
            fontSize: "0.85rem",
          }}
        >
          Best Buy Canada
        </p>
        <h1 style={{ fontSize: "2.25rem", fontWeight: 700 }}>
          Produits en liquidation disponibles à travers tous les magasins Best Buy
        </h1>
        <p style={{ marginTop: "0.75rem", color: "#4b5563", lineHeight: 1.6 }}>
          Ces aubaines proviennent du flux de liquidation Best Buy et sont
          accessibles en ligne pour l’ensemble des succursales. Chaque carte
          mène directement à la page du produit sur bestbuy.ca.
        </p>
        <div style={{ marginTop: "1rem" }}>
          <Link href="/" style={{ color: "#2563eb" }}>
            ← Retour à l’accueil
          </Link>
        </div>
      </header>

      {isLoading && (
        <p style={{ color: "#2563eb", marginBottom: "1rem" }}>
          Chargement des liquidations Best Buy en cours…
        </p>
      )}

      {error && (
        <p style={{ color: "#b91c1c", marginBottom: "1rem" }}>{error}</p>
      )}

      {deals.length === 0 && !isLoading ? (
        <p>Aucune offre de liquidation n’a été trouvée pour le moment.</p>
      ) : (
        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "1.25rem",
          }}
        >
          {deals.map((deal, index) => (
            <article
              key={`${deal.url}-${index}`}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: "0.75rem",
                padding: "1.25rem",
                background: "#fff",
                boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              <h2 style={{ fontSize: "1rem", fontWeight: 600 }}>
                {deal.title}
              </h2>
              <p style={{ color: "#2563eb", fontWeight: 600 }}>
                {formatPrice(deal.price)}
              </p>
              <p style={{ fontSize: "0.9rem", color: "#6b7280" }}>
                Liquidation en ligne – visible pour toutes les succursales Best
                Buy.
              </p>
              <div style={{ marginTop: "auto" }}>
                {deal.url ? (
                  <a
                    href={deal.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-block",
                      marginTop: "0.5rem",
                      padding: "0.5rem 0.9rem",
                      borderRadius: "0.5rem",
                      border: "1px solid #2563eb",
                      color: "#2563eb",
                      fontSize: "0.9rem",
                      fontWeight: 500,
                      textDecoration: "none",
                    }}
                  >
                    Voir le produit
                  </a>
                ) : (
                  <span style={{ color: "#9ca3af", fontSize: "0.9rem" }}>
                    Lien non disponible
                  </span>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
};

export default BestBuyClearancePage;
