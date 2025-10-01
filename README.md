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
- Besoin d'automatiser un import Google Drive ? Consulte `automation/GOOGLE_DRIVE.md`.

© 2025 EconoDeal
