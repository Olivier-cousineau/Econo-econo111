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

## Automatisation

Une action GitHub (`.github/workflows/walmart-scraper.yml`) planifie l'exécution chaque jour à 21h UTC. Pour l'activer :

1. Ajoutez un secret `WALMART_PROXIES` contenant une liste JSON de proxies résidentiels.
2. Personnalisez `incoming/walmart_stores.json` ou la constante `magasins` dans le script.
3. Déclenchez manuellement le workflow via l'onglet **Actions** si nécessaire (`Run workflow`).

Chaque exécution met à jour les JSON par magasin dans `data/walmart/` et attache un artefact `liquidations_walmart_qc.json` téléchargeable depuis GitHub Actions.
