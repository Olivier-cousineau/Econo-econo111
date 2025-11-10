# Workflow Bright Data — Canadian Tire (Store 271)

Ce workflow Bright Data Web Scraper IDE récolte les produits en liquidation du magasin Canadian Tire #271. Il se compose de deux étapes : une première pour lister toutes les fiches produits et une seconde pour extraire les informations détaillées de chaque fiche (prix régulier, prix soldé, rabais, disponibilité, etc.).

## Étape 1 — Listing

**Objectif :** parcourir la page de liquidation, récupérer toutes les URLs produits et suivre la pagination.

```javascript
// INPUT: { url: "https://www.canadiantire.ca/fr/promotions/liquidation.html?store=271" }
navigate(input.url);

// 1) attendre qu'au moins un type de carte apparaisse
const CARD_A = "li[data-testid='product-grids']";
const CARD_B = "li[data-qa='product-grid-item']";
wait(`${CARD_A}, ${CARD_B}`);

// 2) parser la page courante pour récupérer les URLs produits (le Parser ci-dessous renvoie {urls: [...]})
let page_data = parse();
console.log(`Found ${page_data.urls.length} products on current page`);

// 3) envoyer chaque URL à l'étape suivante (on s’assure que le store est présent)
for (let url of page_data.urls) {
  let u = url.includes("store=") ? url : (url + (url.includes("?") ? "&" : "?") + "store=271");
  next_stage({ url: u });
}

// 4) pagination: bouton "Charger plus" OU "Suivant"
const LOAD_MORE = "button:has-text('Charger plus'), button:has-text('Voir plus')";
const NEXT_BTN  = "a[rel='next'], button[aria-label*='Suivant'], a[aria-label*='Suivant'], a[aria-label*='Next']";

if (el_exists(LOAD_MORE) && !attr(LOAD_MORE, "disabled")) {
  console.log("Click LOAD_MORE…");
  click(LOAD_MORE);
  wait(`${CARD_A}, ${CARD_B}`);
  // relance cette étape pour la page suivante
  rerun_stage({ url: location.href });
} else if (el_exists(NEXT_BTN) && !attr(NEXT_BTN, "disabled")) {
  console.log("Click NEXT…");
  click(NEXT_BTN);
  wait(`${CARD_A}, ${CARD_B}`);
  rerun_stage({ url: location.href });
} else {
  console.log("No more pages.");
  set_output({ status: "done" });
}
```

### Parser (Étape 1)

```javascript
// Renvoie toutes les URLs de fiches produits sur la page
const anchors = queryAll("a[href*='/pdp/'], a[href*='/product/']");
const urls = [];
for (let a of anchors) {
  const href = attr(a, "href");
  if (!href) continue;
  let u = href.startsWith("http") ? href : absolute_url(href);
  if (!u.includes("/pdp/") && !u.includes("/product/")) continue;
  urls.push(u.split("#")[0]); // nettoie les #ancres
}
return { urls: Array.from(new Set(urls)) };
```

## Étape 2 — Fiche produit (PDP)

**Objectif :** ouvrir chaque fiche, récupérer les prix actuel/ancien, calculer le rabais et extraire les métadonnées utiles.

```javascript
// INPUT: { url: "<URL fiche produit avec ?store=271>" }
navigate(input.url);
wait("body");
sleep(800); // laisser respirer les scripts prix

let pdp = parse();

// Si pas de prix, scroll + re-parse
if (!pdp.price_now && !pdp.price_was) {
  scroll_to(0, 1200);
  sleep(800);
  const retry = parse();
  if (retry.price_now || retry.price_was) {
    set_output(retry);
  } else {
    set_output(pdp);
  }
} else {
  set_output(pdp);
}
```

### Parser (Étape 2)

```javascript
function num(x) {
  if (!x) return null;
  const m = String(x).replace(/\u00A0/g, " ").match(/(\d{1,5}(?:[.,]\d{2})?)/);
  return m ? parseFloat(m[1].replace(",", ".")) : null;
}

let price_now = null, price_was = null, currency = "CAD";

// 1) JSON-LD (souvent fiable)
const jsonlds = queryAll("script[type='application/ld+json']");
for (let s of jsonlds) {
  try {
    const obj = JSON.parse(text(s));
    const arr = Array.isArray(obj) ? obj : [obj];
    for (let o of arr) {
      if (o && (o["@type"] === "Product" || o["@type"] === "Offer")) {
        const offers = o.offers || o;
        if (offers) {
          if (offers.price) price_now = price_now ?? num(offers.price);
          if (offers.priceCurrency) currency = offers.priceCurrency;
        }
      }
    }
  } catch(e) {}
}

// 2) Fallback DOM — prix actuel & prix “était”
price_now = price_now ??
  num(text(".nl-price--total--red")) ??
  num(text(".nl-price--total")) ??
  num(text("[data-automation='sale-price']")) ??
  num(text("[data-automation='current-price']"));

price_was =
  num(text(".nl-price--was")) ??
  num(text(".sr-only")) ??
  num(text("[data-automation='was-price']"));

// 3) autres champs
const title = text("h1, [data-automation='product-title'], .pdp-product-title") || "";
const image = attr("img[alt][src*='product'], img[loading='eager']", "src") || "";
const sku = (text("[data-automation='product-code'], .product__code") || "").replace(/^#/, "").trim();
const availability = text("[data-automation='availability'], .availability, .store-availability") || "";
const brand = text("[data-automation='brand'], .product-brand, .brand") || "";
const tag = (text(".badge, .nl-rebate-header, .product-badge") || "").trim() || "";

// 4) rabais
let discount_pct = null;
if (price_now != null && price_was != null && price_was > 0 && price_now <= price_was) {
  discount_pct = Math.round(((price_was - price_now) / price_was) * 100);
}

return {
  title,
  brand,
  price_now,
  price_was,
  discount_pct,
  currency,
  availability,
  image,
  sku,
  link: url(),
  tag
};
```

## Sortie attendue

Chaque exécution fournit un enregistrement par produit comprenant :

- `title`, `brand`, `sku`
- `price_now`, `price_was`, `discount_pct`, `currency`
- `availability`, `tag`
- `image`, `link`

En exportant les résultats Bright Data au format JSON ou CSV, on obtient un inventaire complet des rabais Canadian Tire pour le magasin #271 prêt à être intégré dans les tableaux de bord EconoDeal.
