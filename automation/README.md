# Automatisation des liquidations Canadian Tire

Ce dossier contient un exemple complet de scraper Python qui récupère les
produits en liquidation de plusieurs succursales Canadian Tire du Québec puis
les injecte sur votre site web.

> ⚠️ Les API internes de Canadian Tire ne sont pas publiques. Le script fourni
> ici repose sur des points de terminaison observés publiquement et peut cesser
> de fonctionner à tout moment. Adaptez le code en fonction de vos propres
> tests et respectez les conditions d'utilisation du site.

## Structure

- `scraper.py` – script principal (ligne de commande).
- `config.example.json` – configuration à dupliquer et personnaliser (`cp config.example.json config.json`).
- `requirements.txt` – dépendances Python minimales.
- `liquidations.sqlite` – base SQLite créée au premier lancement (peut être changée via `--database`).
- `canadian_tire_stores_qc.json` – annuaire des succursales Canadian Tire du Québec utilisé pour compléter automatiquement les métadonnées.

## Préparation de l'environnement

```bash
cd automation
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

Modifiez `config.json` pour y inscrire :

- La liste des succursales (identifiant Canadian Tire `store_id`). Le fichier `canadian_tire_stores_qc.json` fournit plus de 80 emplacements québécois avec leur slug; complétez le `store_id` pour ceux que vous ciblez.
- Les départements / mots-clés à cibler.
- L'URL d'injection de votre site (`site_endpoint.url`) ainsi que le token API si nécessaire.

## Lancer le scraper

```bash
python scraper.py --log-level INFO
```

Options utiles :

- `--dry-run` : n'envoie pas les données vers votre site, affiche simplement un résumé.
- `--config /chemin/vers/config.json`
- `--database /chemin/vers/liquidations.sqlite`
- `--list-stores` : affiche l'annuaire `canadian_tire_stores_qc.json` avec les slugs à utiliser dans vos configurations.

À chaque exécution, le script :

1. Télécharge les liquidations pour chaque succursale configurée.
2. Enregistre les produits dans la base SQLite (`INSERT ... ON CONFLICT`).
3. Transmet les produits à votre site via `POST` JSON (sauf `--dry-run`).

## Planification quotidienne (17h, heure du Québec)

Activez l'environnement virtuel et créez un script shell `run-scraper.sh` :

```bash
#!/bin/bash
cd /chemin/vers/Econo-econo111/automation
source .venv/bin/activate
python scraper.py --log-level INFO >> scraper.log 2>&1
```

Ensuite, ajoutez la tâche Cron :

```bash
crontab -e
```

```
0 17 * * * /chemin/vers/Econo-econo111/automation/run-scraper.sh
```

Le fuseau horaire `America/Toronto` couvre le Québec (EST/EDT). Si votre
serveur utilise un autre fuseau, ajustez la tâche cron ou le champ `timezone`
dans `config.json`.

## Intégration côté site

L'endpoint appelé reçoit un JSON du type :

```json
{
  "store_id": "0474",
  "store_nickname": "Québec - Lebourgneuf",
  "items": [
    {
      "sku": "123-4567",
      "name": "Scie circulaire",
      "price_regular": 249.99,
      "price_clearance": 149.99,
      "discount_percent": 40.0,
      "product_url": "https://www.canadiantire.ca/fr/pdp/1234567.html",
      "image_url": "https://.../1234567.jpg"
    }
  ]
}
```

Libre à vous de consommer ce JSON et de l'intégrer à votre site (ex. insertion
SQL, indexation Elasticsearch, génération de fichier `.json` dans `data/`).

## Dépannage

- Activez `--log-level DEBUG` pour voir les URLs exactes et les payloads.
- Vérifiez que l'ID de succursale (`store_id`) est correct dans le réseau de
  Canadian Tire.
- Si le site change sa structure, adaptez `_parse_from_json` et `_parse_from_html`.
- Consultez `liquidations.sqlite` avec `sqlite3` ou un outil GUI pour valider les
  données ingérées.
