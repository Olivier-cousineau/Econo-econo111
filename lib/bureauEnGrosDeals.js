export function parseBureauEnGrosSlug(slug) {
  const parts = typeof slug === "string" ? slug.split("-") : [];
  const id = parts[0] ?? slug ?? "";

  const cityAndProvince = parts.slice(4).join(" ") || slug || "";
  const label = `Bureau en Gros – ${cityAndProvince.toUpperCase()}`;

  return { id, cityAndProvince, label };
}

export function buildBureauEnGrosStore(slug, productCount = 0, jsonPath = null) {
  const { id, label } = parseBureauEnGrosSlug(slug);

  return {
    slug,
    id,
    label,
    jsonPath,
    productCount,
  };
}

export function filterVisibleBureauEnGrosDeals(deals) {
  if (!Array.isArray(deals)) return [];

  return deals.filter((deal) => {
    const hasTitle = !!deal.title;
    const hasPrice =
      deal.priceCurrent !== null &&
      deal.priceCurrent !== undefined &&
      deal.priceCurrent !== "";

    return hasTitle && hasPrice;
  });
}
