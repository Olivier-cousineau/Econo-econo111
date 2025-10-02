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

## Aperçus HTML rapides
- Les jeux de données organisés génèrent un aperçu statique dans `previews/<magasin>/<ville>.html`.
- Par exemple : `previews/sporting-life/montreal.html`, `previews/sporting-life/laval.html` et
  `previews/sporting-life/saint-jerome.html` permettent de feuilleter les aubaines Sporting Life
  directement depuis GitHub sans devoir lancer le site.

© 2025 EconoDeal

## Automatisation du scraper Walmart

Le script asynchrone `incoming/walmart_scraper.py` peut tourner automatiquement via
GitHub Actions :

1. Dans **Settings → Secrets and variables → Actions**, ajoute un secret
   `WALMART_PROXIES` contenant ta liste JSON de proxies, par exemple :
   `[
   "http://user:pass@proxy1:port", "http://user:pass@proxy2:port"
   ]`.
2. Complète la liste `magasins` dans le script (ou crée un fichier
   `incoming/walmart_stores.json`) avec l'identifiant, la ville et l'adresse de
   chacun des magasins.
3. Le workflow `.github/workflows/walmart-scraper.yml` s'exécute chaque jour à
   **17 h (heure de l'Est)**, ce qui correspond à 21 h UTC.
4. Pour lancer le scraper manuellement vers 16 h, ouvre l'onglet **Actions**,
   sélectionne *Walmart liquidation scraper* puis clique sur **Run workflow**.
   Tu peux ajouter une note facultative avant de déclencher l'exécution.

Chaque exécution produit un fichier `liquidations_walmart_qc.json` et le met à
disposition en tant qu'artéfact téléchargeable depuis l'interface des Actions.
Les jeux de données par magasin sont également mis à jour dans `data/walmart/`
(`data/walmart/laval.json`, `data/walmart/moncton.json`, etc.) afin d'être
consommés directement par le site statique.
