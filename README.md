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

## Exécution du scraper Walmart

Le script asynchrone `incoming/walmart_scraper.py` peut être exécuté à la demande
depuis ton poste de travail :

1. Crée un fichier `incoming/walmart_stores.json` ou complète la liste `magasins`
   avec l'identifiant, la ville et l'adresse de chaque magasin.
2. Lance le script avec `python incoming/walmart_scraper.py` après avoir défini la
   variable d'environnement `WALMART_PROXIES` contenant ta liste JSON de proxies :
   `[
   "http://user:pass@proxy1:port", "http://user:pass@proxy2:port"
   ]`.
3. Récupère les résultats dans `liquidations_walmart_qc.json` ainsi que dans les
   fichiers par magasin présents dans `data/walmart/` (`data/walmart/laval.json`,
   `data/walmart/moncton.json`, etc.). Ces jeux de données peuvent ensuite être
   consommés directement par le site statique.
