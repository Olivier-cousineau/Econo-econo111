# Données Best Buy

Ce dossier reçoit les fichiers JSON produits par le script `incoming/best_buy_scraper.py`.

## Fichiers

- `stores.json` – Liste des magasins québécois (identifiant Best Buy, ville, adresse).
- `liquidations.json` – Agrégat global des aubaines en liquidation pour tous les magasins traités.
- `<slug>.json` – Fichier par magasin généré lors d'une exécution du scraper.

## Mise à jour

```bash
python incoming/best_buy_scraper.py --language fr
```

Vous pouvez cibler un ou plusieurs magasins précis :

```bash
python incoming/best_buy_scraper.py --store laval --store "Trois-Rivieres"
```

Le script accepte également `--language en`, `--output-dir`, `--aggregated-path`,
`--max-retries`, `--timeout`, `--delay` et `--page-size`.

Les fichiers générés remplacent ceux existants; assurez-vous d'effectuer un commit
des résultats avant de pousser vers GitHub.
