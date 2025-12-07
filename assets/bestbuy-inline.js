document.addEventListener('DOMContentLoaded', () => {
  const storeSelect     = document.getElementById('storeSelect');
  const citySelect      = document.getElementById('citySelect');
  const searchInput     = document.getElementById('searchInput');
  const discountRange   = document.getElementById('discountRange');
  const resultCount     = document.getElementById('resultCount');
  const cardsContainer  = document.getElementById('cards');
  const devError        = document.getElementById('devError');

  if (!storeSelect || !cardsContainer) return;

  // Liste statique de villes Best Buy – pour que le sélecteur ville continue
  // d'afficher des succursales, même si le JSON ne contient pas la ville.
  const BESTBUY_CITIES = [
    'En ligne (Canada)',
    'St. Jerome',
    'Rosemere',
    'Mascouche',
    'Laval',
    'Pointe Claire',
    'Marche Central',
    'Vaudreuil',
    'Centreville'
  ];

  let bestBuyDealsCache = null;

  async function loadBestBuyDeals() {
    if (bestBuyDealsCache) return bestBuyDealsCache;

    try {
      // IMPORTANT : chemin relatif, sans "/" au début,
      // pour servir le fichier statique sur Vercel.
      const resp = await fetch('bestbuy/clearance.json', { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);

      const raw = await resp.json();

      bestBuyDealsCache = raw.map((item, index) => {
        const priceNumber =
          typeof item.price === 'number'
            ? item.price
            : parseFloat(
                String(item.price)
                  .replace(/[^0-9.,]/g, '')
                  .replace(',', '.')
              );

        return {
          id: 'bestbuy-' + index,
          title: item.title ?? '',
          url: item.url ?? '#',
          price: Number.isFinite(priceNumber) ? priceNumber : null,
          discountPercent: 0 // pour l'instant on ne connaît pas le rabais exact
        };
      });

      console.log('[BestBuy-inline] deals chargés :', bestBuyDealsCache.length);
      if (devError) {
        devError.textContent = `[BestBuy] ${bestBuyDealsCache.length} deals chargés depuis clearance.json`;
      }
    } catch (err) {
      console.error('[BestBuy-inline] Erreur de chargement clearance.json', err);
      bestBuyDealsCache = [];
      if (devError) {
        devError.textContent = '[BestBuy] Erreur : ' + err.message;
      }
    }

    return bestBuyDealsCache;
  }

  function isBestBuySelected() {
    if (!storeSelect) return false;
    const label = storeSelect.options[storeSelect.selectedIndex]?.textContent || '';
    const value = storeSelect.value || '';
    return /best\s*buy/i.test(label) || /bestbuy/i.test(value);
  }

  function ensureBestBuyCitiesOptions() {
    if (!citySelect) return;
    if (!isBestBuySelected()) return;

    // Si on a déjà plus d'une option, on ne touche pas
    if (citySelect.options.length > 1) return;

    // On reconstruit : (Toutes) + toutes les villes Best Buy
    citySelect.innerHTML = '';
    const optAll = document.createElement('option');
    optAll.value = '';
    optAll.textContent = '(Toutes)';
    citySelect.appendChild(optAll);

    BESTBUY_CITIES.forEach(city => {
      const opt = document.createElement('option');
      opt.value = city;
      opt.textContent = city;
      citySelect.appendChild(opt);
    });
  }

  function applyFilters(deals) {
    const q = (searchInput?.value || '').trim().toLowerCase();
    const minDiscount = Number(discountRange?.value || '0');

    return deals.filter(d => {
      if (q && !d.title.toLowerCase().includes(q)) return false;
      if (minDiscount > 0 && (d.discountPercent || 0) < minDiscount) return false;
      // Pour l'instant, on ignore le filtre "ville" pour Best Buy :
      // même inventaire pour toutes les succursales.
      return true;
    });
  }

  function renderBestBuyCards(deals) {
    cardsContainer.innerHTML = '';

    if (!deals.length) {
      resultCount.textContent = '0';
      return;
    }

    deals.forEach(d => {
      const card = document.createElement('article');
      card.className = 'deal-card';

      const priceHtml =
        d.price != null
          ? `<span class="deal-price-current">${d.price.toFixed(2)} $</span>`
          : '';

      card.innerHTML = `
        <a class="deal-card-link" href="${d.url}" target="_blank" rel="noopener">
          <div class="deal-card-header">
            <span class="deal-store">Best Buy</span>
            <span class="deal-discount">${d.discountPercent || 0}% Rabais</span>
          </div>
          <h4 class="deal-title">${d.title}</h4>
          <div class="deal-price">
            ${priceHtml}
          </div>
        </a>
      `;

      cardsContainer.appendChild(card);
    });

    resultCount.textContent = String(deals.length);
  }

  async function refreshBestBuyIfNeeded() {
    if (!isBestBuySelected()) return;

    ensureBestBuyCitiesOptions();

    const allDeals = await loadBestBuyDeals();
    const filtered = applyFilters(allDeals);
    renderBestBuyCards(filtered);
  }

  // Quand on change de magasin, on laisse l'ancien code tourner,
  // puis on applique Best Buy par-dessus si besoin.
  storeSelect.addEventListener('change', () => {
    setTimeout(refreshBestBuyIfNeeded, 0);
  });

  // Rafraîchir Best Buy quand on tape ou qu’on bouge le slider
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      setTimeout(refreshBestBuyIfNeeded, 0);
    });
  }
  if (discountRange) {
    discountRange.addEventListener('input', () => {
      setTimeout(refreshBestBuyIfNeeded, 0);
    });
  }

  // Premier chargement : si Best Buy est déjà sélectionné, on charge les deals.
  setTimeout(() => {
    if (isBestBuySelected()) {
      ensureBestBuyCitiesOptions();
      refreshBestBuyIfNeeded();
    }
  }, 0);
});
