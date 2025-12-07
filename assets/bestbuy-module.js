(async () => {
  const cards = document.getElementById("cards");
  const resultCount = document.getElementById("resultCount");
  const devError = document.getElementById("devError");
  const searchInput = document.getElementById("searchInput");
  const storeSelect = document.getElementById("storeSelect");
  const citySelect = document.getElementById("citySelect");
  const postalInput = document.getElementById("postalInput");
  const discountRange = document.getElementById("discountRange");
  const discountValue = document.getElementById("discountValue");
  const clearBtn = document.getElementById("btnClear");

  if (!cards || !resultCount || !storeSelect) {
    console.warn("[BestBuy] éléments de filtrage introuvables, script ignoré.");
    return;
  }

  async function loadBestBuyClearance() {
    const url = "./outputs/bestbuy/clearance.json";
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const raw = await res.json();
      if (!Array.isArray(raw)) {
        throw new Error("JSON BestBuy invalide");
      }

      return raw.map((item, index) => {
        const priceNumber =
          typeof item.price === "number"
            ? item.price
            : parseFloat(
                String(item.price || "")
                  .replace(/[^0-9.,]/g, "")
                  .replace(",", ".")
              );

        return {
          id: `bestbuy-${index}`,
          store: "Best Buy",
          city: null,
          postalPrefix: null,
          title: item.title || "Produit Best Buy",
          url: item.url || "#",
          currentPrice: Number.isFinite(priceNumber) ? priceNumber : null,
          discountPercent: null,
        };
      });
    } catch (err) {
      console.error("[BestBuy] Erreur de chargement du JSON:", err);
      if (devError) {
        devError.textContent =
          "Impossible de charger les liquidations Best Buy (clearance.json).";
      }
      return [];
    }
  }

  function renderCards(deals) {
    cards.innerHTML = "";
    resultCount.textContent = deals.length.toString();

    if (!deals.length) {
      cards.innerHTML =
        '<p class="muted">Aucun résultat pour ces filtres.</p>';
      return;
    }

    const frag = document.createDocumentFragment();

    for (const deal of deals) {
      const article = document.createElement("article");
      article.className = "deal-card";

      const title = document.createElement("h4");
      title.className = "deal-title";
      title.textContent = deal.title;

      const meta = document.createElement("div");
      meta.className = "deal-meta";

      const storeSpan = document.createElement("span");
      storeSpan.textContent = deal.store;

      const priceSpan = document.createElement("span");
      if (deal.currentPrice != null) {
        priceSpan.textContent = deal.currentPrice.toFixed(2) + " $";
      } else {
        priceSpan.textContent = "Prix inconnu";
      }

      meta.appendChild(storeSpan);
      meta.appendChild(priceSpan);

      const link = document.createElement("a");
      link.className = "deal-link";
      link.href = deal.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Voir le produit chez Best Buy";

      article.appendChild(title);
      article.appendChild(meta);
      article.appendChild(link);

      frag.appendChild(article);
    }

    cards.appendChild(frag);
  }

  let allBestBuyDeals = [];

  function applyFilters() {
    const search = (searchInput?.value || "").trim().toLowerCase();
    const storeFilter = storeSelect.value;
    const cityFilter = citySelect.value;
    const minDiscount = Number(discountRange?.value || 0);
    const postalPrefix = (postalInput?.value || "")
      .trim()
      .toUpperCase()
      .slice(0, 3);

    let list = allBestBuyDeals;

    if (storeFilter && storeFilter !== "bestbuy" && storeFilter !== "Best Buy") {
      renderCards([]);
      return;
    }

    list = list.filter((deal) => {
      if (cityFilter && deal.city && deal.city !== cityFilter) return false;

      if (postalPrefix && deal.postalPrefix) {
        if (!deal.postalPrefix.startsWith(postalPrefix)) return false;
      }

      if (minDiscount > 0) {
        const dealDiscount =
          typeof deal.discountPercent === "number" ? deal.discountPercent : 0;

        if (dealDiscount < minDiscount) return false;
      }

      if (search) {
        const haystack = deal.title.toLowerCase();
        if (!haystack.includes(search)) return false;
      }

      return true;
    });

    renderCards(list);
  }

  const bestBuyDeals = await loadBestBuyClearance();
  allBestBuyDeals = bestBuyDeals;

  const hasBestBuyOption = Array.from(storeSelect.options).some(
    (opt) =>
      opt.value === "bestbuy" ||
      opt.value === "Best Buy" ||
      opt.textContent === "Best Buy"
  );

  if (!hasBestBuyOption) {
    const opt = document.createElement("option");
    opt.value = "bestbuy";
    opt.textContent = "Best Buy";
    storeSelect.appendChild(opt);
  }

  storeSelect.value = "bestbuy";
  applyFilters();

  if (searchInput) searchInput.addEventListener("input", applyFilters);
  if (discountRange) {
    discountRange.addEventListener("input", () => {
      if (discountValue) discountValue.textContent = discountRange.value + "%";
      applyFilters();
    });
  }
  if (storeSelect) storeSelect.addEventListener("change", applyFilters);
  if (citySelect) citySelect.addEventListener("change", applyFilters);
  if (postalInput) postalInput.addEventListener("input", applyFilters);
  if (clearBtn) {
    clearBtn.addEventListener("click", (event) => {
      event.preventDefault();
      if (searchInput) searchInput.value = "";
      if (postalInput) postalInput.value = "";
      if (discountRange) {
        discountRange.value = "0";
        if (discountValue) discountValue.textContent = "0%";
      }
      storeSelect.value = "bestbuy";
      citySelect.value = "";
      applyFilters();
    });
  }
})();
