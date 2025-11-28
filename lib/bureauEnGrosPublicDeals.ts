export type BureauEnGrosPublicData = {
  storeId: string;
  storeName: string;
  count: number;
  products: any[];
};

export async function fetchBureauEnGrosDealsFromPublic(
  storeSlug: string
): Promise<BureauEnGrosPublicData> {
  if (!storeSlug || typeof storeSlug !== "string") {
    throw new Error("Missing Bureau en Gros store slug");
  }

  const url = `/bureauengros/${storeSlug}/data.json`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `Failed to load Bureau en Gros deals for ${storeSlug} (${response.status})`
    );
  }

  let payload: any;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error("Invalid Bureau en Gros response JSON");
  }

  const products = Array.isArray(payload?.products) ? payload.products : [];
  const count =
    typeof payload?.count === "number" ? payload.count : products.length;

  return {
    storeId: String(
      payload?.storeId ?? payload?.store?.id ?? payload?.store_id ?? ""
    ),
    storeName: String(payload?.storeName ?? payload?.store?.name ?? "").trim(),
    count,
    products,
  };
}
