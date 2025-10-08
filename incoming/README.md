# Walmart Liquidation Scraper

Ce dossier contient le script Python asynchrone utilisé pour récupérer les produits en liquidation publiés sur les pages locales de Walmart Canada.

## Installation locale rapide

```bash
python -m venv .venv
source .venv/bin/activate  # PowerShell: .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
playwright install --with-deps chromium
```

> 💡 Le script repose sur Playwright. L'installation du navigateur Chromium est nécessaire lors du premier lancement (voir la commande `playwright install` ci-dessus).

## Lancer une extraction

```bash
python incoming/walmart_scraper.py
```

Quelques options pratiques :

| Option | Description |
| --- | --- |
| `--store laval` | Limite l'extraction à un magasin (ID, ville ou slug). |
| `--store laval --store montreal` | Peut être répété pour cumuler plusieurs magasins. |
| `--no-headless` | Affiche Chromium pendant l'exécution (utile pour déboguer). |
| `--output-dir ./sorties` | Sauvegarde les JSON des magasins dans un dossier personnalisé. |
| `--aggregated-path ./sorties/liquidations.json` | Définit le fichier d'agrégation final. |
| `--max-concurrent-browsers 1` | Réduit la concurrence si votre machine est limitée. |

Le script crée un fichier `liquidations_walmart_qc.json` (agrégat global) et un fichier JSON par magasin dans `data/walmart/` (ou dans le dossier fourni via `--output-dir`).

### Variante HTTP (sans navigateur)

Pour un environnement plus contraint (ex.: exécution locale rapide ou proxy HTTP dédié), le script `incoming/walmart_requests_scraper.py` effectue la même extraction à l'aide de requêtes `requests`/`BeautifulSoup`.

```bash
python incoming/walmart_requests_scraper.py --store saint-jerome
```

Les options (`--store`, `--output-dir`, `--aggregated-path`, etc.) sont identiques à la version Playwright. Ce scraper repose sur la disponibilité du JSON `__NEXT_DATA__` dans la page et peut échouer si Walmart modifie la structure. En contrepartie, il démarre en quelques secondes et nécessite moins de ressources.

## Planification manuelle

Pour exécuter le scraper à intervalles réguliers, créez votre propre planificateur (ex.: cron, tâche planifiée) qui appelle la commande `python incoming/walmart_scraper.py`. Assurez-vous que la variable `WALMART_PROXIES` est définie dans l'environnement d'exécution et que les fichiers de sortie sont synchronisés avec votre environnement de production.

# Canadian Tire Clearance Scraper

Le script `incoming/canadian_tire_scraper.py` gère la récupération des produits en liquidation publiés par Canadian Tire. Il lit la liste des magasins depuis `data/canadian-tire/stores.json`, génère un fichier JSON par magasin dans `data/canadian-tire/` puis consolide l'ensemble dans un agrégat global.

```bash
python incoming/canadian_tire_scraper.py --store laval --store saint-jerome
```

Options principales :

| Option | Description |
| --- | --- |
| `--store` | Peut être répété pour sélectionner des magasins précis (ID, slug, ville). |
| `--language` | Force la langue des pages magasin ciblées (`fr` ou `en`). |
| `--output-dir` | Change le dossier de sortie pour les fichiers par magasin. |
| `--aggregated-path` | Déplace le fichier d'agrégation (défaut : `liquidations_canadian_tire_qc.json`). |
| `--max-retries`, `--timeout`, `--delay` | Ajustent la tolérance réseau. |

Chaque exécution sauvegarde les aubaines dans `data/canadian-tire/<ville>.json` et regroupe l'ensemble dans `liquidations_canadian_tire_qc.json`.

# Best Buy Clearance Scraper

Le script `incoming/best_buy_scraper.py` automatise la récupération des offres en liquidation affichées dans les magasins Best Buy du Québec. Il produit un fichier JSON par magasin (dossier `data/best-buy/`) et un agrégat global (`liquidations.json`).

```bash
python incoming/best_buy_scraper.py --language fr
```

Options principales :

| Option | Description |
| --- | --- |
| `--store laval` | Limite l'extraction à un magasin (ville, label, slug ou numéro). |
| `--language en` | Retourne les données en anglais (`fr` par défaut). |
| `--output-dir ./sorties` | Change le dossier cible pour les JSON individuels. |
| `--aggregated-path ./sorties/liquidations.json` | Positionne l'agrégat global. |
| `--page-size 200` | Ajuste le nombre de produits chargés par requête. |
| `--max-retries`, `--timeout`, `--delay` | Affinent la résilience réseau. |

⚠️ L'API Best Buy applique des mécanismes anti-robot. En cas d'erreur 403, augmentez les délais (`--delay 2 5`) et réduisez la fréquence d'exécution.
