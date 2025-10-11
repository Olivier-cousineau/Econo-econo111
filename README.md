# EconoDeal (Static)

Site statique bilingue (FR/EN) avec filtres Magasin/Ville et barre de % de rabais.

## Déploiement rapide

### GitHub Pages
1. Crée un nouveau repo `econodeal-site` sur GitHub.
2. Pousse ces fichiers (`index.html`, dossier `data/`, etc.).
3. Dans **Settings > Pages**, choisis branch `main` et dossier `/root`.
4. L'URL sera disponible après quelques minutes.

### Vercel
1. Import le repo sur Vercel.
2. Build command: *(aucune)* — Framework: **Other** (site statique).
3. Déploie — l'URL est prête.
4. Tu peux remplacer le contenu de `render()` pour charger tes JSON.

## Brancher tes données
- Dépose tes JSON dans `/data` (voir `/data/README.md`).
- Dans `index.html`, remplace `render()` pour faire des `fetch('/data/ton_fichier.json')`,
  merger les tableaux, appliquer les filtres et générer les cartes.

## Automatiser Amazon Canada (PA API)
Un utilitaire est fourni pour rapatrier quotidiennement des produits Amazon Canada
et alimenter `/data`.

1. Installe la dépendance : `pip install requests`.
2. Exporte tes identifiants Amazon Associates :
   ```bash
   export PAAPI_CLIENT_ID="amzn1.application-oa2-client..."
   export PAAPI_CLIENT_SECRET="<ta_clé_secrète>"
   export PAAPI_ASSOCIATE_TAG="ton-tag-20"
   ```
3. Ajuste la liste de mots-clés dans `admin/amazon_keywords.json` (ou passe `--keywords`).
4. Lance le script :
   ```bash
   python admin/amazon_paapi_daily.py --limit 8
   ```
   - Le JSON généré est sauvegardé dans `data/amazon_ca_daily.json`.
   - En cas d'erreur API, des aubaines fictives cohérentes seront générées pour garder
     la page active.
   - Pour tester sans identifiants, ajoute `--no-api` afin de générer uniquement les aubaines
     fictives ; tu peux ensuite ouvrir `data/amazon_ca_daily.json` pour valider la structure.
5. Pour une mise à jour automatique, planifie la commande via `cron`, GitHub Actions,
   ou un autre ordonnanceur quotidien.

### GitHub Actions prêt à l'emploi
Un workflow `Refresh Amazon Canada deals` est fourni dans `.github/workflows/amazon-daily.yml`.

1. Dans GitHub, va dans **Settings ▸ Secrets and variables ▸ Actions** et ajoute les
   secrets `PAAPI_CLIENT_ID`, `PAAPI_CLIENT_SECRET` et `PAAPI_ASSOCIATE_TAG` avec tes
   identifiants Amazon Associates.
2. Active l'onglet **Actions** et lance `Refresh Amazon Canada deals` en cliquant sur
   **Run workflow** pour un test manuel. Chaque exécution génère `data/amazon_ca_daily.json`
   (avec un fallback fictif si les secrets sont absents ou invalides) et exécute le test
   unitaire `tests.test_amazon_paapi_daily`.
3. Dès que le fichier est présent sur la branche `main`, le workflow s'exécute aussi
   automatiquement à chaque push affectant les fichiers Amazon, ce qui le rend visible
   dans l'onglet **Actions** sans attendre la première planification.
4. Le workflow tourne ensuite tous les jours à 09:00 UTC et commit automatiquement le
   fichier `data/amazon_ca_daily.json` lorsqu'il change. Ajuste la valeur `cron` ou les
   paramètres (ex. `--limit`) dans `amazon-daily.yml` selon tes besoins.

## Aperçus HTML rapides
- Les jeux de données organisés génèrent un aperçu statique dans `previews/<magasin>/<ville>.html`.
- Par exemple : `previews/sporting-life/montreal.html`, `previews/sporting-life/laval.html` et
  `previews/sporting-life/saint-jerome.html` permettent de feuilleter les aubaines Sporting Life
  directement depuis GitHub sans devoir lancer le site.

> ℹ️ Les jeux de données historiques hors Amazon restent à mettre à jour manuellement en
ajoutant ou remplaçant les fichiers JSON dans `data/`.

## Tests rapides
- Vérifie que le script Amazon reste fonctionnel avec :
  ```bash
  python -m unittest tests/test_amazon_paapi_daily.py
  ```
  Cette suite exécute le script en mode `--no-api` et s'assure que le fichier JSON généré respecte
  le schéma attendu (titres, prix, URL, etc.).

© 2025 EconoDeal
