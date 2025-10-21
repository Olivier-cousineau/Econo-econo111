# EconoDeal (Static)

Site statique bilingue (FR/EN) avec filtres Magasin/Ville et barre de % de rabais.

## Déploiement rapide

### GitHub Pages
1. Crée un nouveau repo `econodeal-site` sur GitHub.
2. Pousse ces fichiers (`index.html`, dossier `data/`, etc.).
3. Dans **Settings > Pages**, choisis branch `main` et dossier `/root`.
4. L'URL sera disponible après quelques minutes.

### Vercel
1. Déploie la page HTML directement. Si ton projet est en Next.js, tu peux garder ce fichier pour forcer les runtimes personnalisés.
2. Si tu veux utiliser Python
   - Utilise le runtime officiel, par exemple :
     ```json
     {
       "functions": {
         "api/**/*.py": { "runtime": "python3.11" }
       }
     }
     ```
   - Les runtimes valides sont : `nodejs18.x`, `python3.11`, etc.
3. Si ton projet est 100 % Next.js (React)
   - Tu peux simplement supprimer le fichier `vercel.json` (ou enlever la partie `functions`).

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
5. Pour une mise à jour automatique, planifie la commande via `cron`, GitHub Actions,
   ou un autre ordonnanceur quotidien.

> ℹ️ Le script `sandbox_deals.py` qui génère des réponses fictives à partir du
> bac à sable Amazon dépend de la bibliothèque optionnelle `paapi5-python-sdk`.
> Cette dernière n'est pas compatible avec Python 3.12 (la version utilisée par
> Vercel). Exécute ce script uniquement dans un environnement Python 3.11 (ou
> antérieur) où tu peux installer manuellement `pip install paapi5-python-sdk`.

## Scraper Sporting Life (liquidations)

Un scraper résilient est disponible dans `admin/sportinglife_liquidations.py` pour
collecter automatiquement les aubaines de la page liquidation de Sporting Life et
les pousser vers l'API EconoDeal.

### Installation

1. Installe les dépendances Python communes :
   ```bash
   pip install -r requirements.txt
   ```
2. Installe les moteurs Playwright (une seule fois) :
   ```bash
   playwright install chromium
   ```

### Exécution manuelle

1. Exporte ton token API (Bearer) :
   ```bash
   export SPORTINGLIFE_API_TOKEN="<ton_token_api>"
   ```
2. Lance le script :
   ```bash
   python admin/sportinglife_liquidations.py \
     --output /home/econodeal/data/liquidations_sportinglife.json \
     --log-file /home/econodeal/logs/sportinglife_scraper.log
   ```
   - Le fichier JSON n'est remplacé que lorsque la collecte aboutit.
   - Le journal détaillé est conservé dans `logs/` (et sur STDOUT).
   - Utilise `--skip-upload` pour n'écrire que le fichier local.

Variables d'environnement disponibles :

- `SPORTINGLIFE_LIQUIDATION_URL` : URL de la page à surveiller.
- `SPORTINGLIFE_OUTPUT_FILE` : chemin par défaut du fichier JSON.
- `SPORTINGLIFE_API_URL` : endpoint d'import EconoDeal.
- `SPORTINGLIFE_API_TOKEN` : jeton Bearer pour l'import.
- `SPORTINGLIFE_LOG_FILE`, `SPORTINGLIFE_MAX_RETRIES`, etc., pour ajuster les
  paramètres de temps et de log.

### Planification quotidienne (cron)

Pour mettre à jour les liquidations tous les jours à 4 h (heure du Pacifique) :

```bash
sudo timedatectl set-timezone America/Vancouver
crontab -e
```

Ajoute la ligne suivante (adapter les chemins si besoin) :

```bash
0 4 * * * /usr/bin/python3 /home/econodeal/admin/sportinglife_liquidations.py \
  --output /home/econodeal/data/liquidations_sportinglife.json \
  --log-file /home/econodeal/logs/sportinglife_scraper.log >> /home/econodeal/logs/cron.log 2>&1
```

Le script journalise automatiquement les tentatives, change d'agent utilisateur à
chaque exécution et réessaie en cas d'échec réseau ou de chargement dynamique.

### Via GitHub Actions (Daily Amazon Deals)

Le dépôt inclut déjà un workflow (`.github/workflows/amazon-deals.yml`) qui exécute
le script tous les jours à 09:30 UTC et pousse `data/amazon_ca_daily.json` avec le
message `chore: update Amazon deals feed`.

1. Dans **Settings → Secrets and variables → Actions**, ajoute les secrets
   `PAAPI_CLIENT_ID`, `PAAPI_CLIENT_SECRET` et `PAAPI_ASSOCIATE_TAG`.
2. Vérifie l'horaire ou adapte la clé `cron` si nécessaire.
3. Pour lancer une mise à jour manuelle, ouvre l'onglet **Actions**, choisis
   **Daily Amazon Deals** puis clique sur **Run workflow** (option disponible via
   l'événement `workflow_dispatch`).
4. Consulte les journaux du job `fetch-deals` pour confirmer si l'API a répondu ou
   si des données fictives ont été générées.
   - Le workflow réussit lorsqu'il affiche une succession d'étapes similaires à :
     `Set up job`, `Check out repository`, `Set up Python`, `Install dependencies`,
     `Generate Amazon deals dataset`, `Commit updated dataset` et `Complete job`.
     Si l'une de ces étapes échoue ou n'apparaît pas, inspecte ses logs détaillés
     pour diagnostiquer le problème (ex. identifiants manquants ou erreurs réseau).

## Aperçus HTML rapides
- Les jeux de données organisés génèrent un aperçu statique dans `previews/<magasin>/<ville>.html`.
- Par exemple : `previews/sporting-life/montreal.html`, `previews/sporting-life/laval.html` et
  `previews/sporting-life/saint-jerome.html` permettent de feuilleter les aubaines Sporting Life
  directement depuis GitHub sans devoir lancer le site.

> ℹ️ Toutes les automatisations ont été retirées. La mise à jour des données et des aperçus se fait
manuellement en ajoutant ou en remplaçant les fichiers JSON dans `data/`.

## Activer la billetterie Stripe (checkout)

Une intégration Stripe Checkout est disponible sur les pages `pricing*.html` pour encaisser les
abonnements.

1. Dupliquez le fichier `.env.example` en `.env` et remplacez les clés par vos identifiants Stripe
   (utilisez les clés test pour vos essais locaux). Le serveur lit la variable
   `STRIPE_PUBLISHABLE_KEY`, mais acceptera aussi `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` si votre
   frontend utilise déjà cette convention.
2. Installez les dépendances Python supplémentaires :
   ```bash
   pip install -r requirements.txt
   ```
3. Les fonctions backend (`/config` et `/create-checkout-session`) chargent désormais automatiquement
   les variables définies dans `.env` ou `.env.local`. Vous pouvez toujours exporter manuellement
   vos variables d'environnement si vous préférez.
4. Lancez le serveur Flask fourni pour exposer les endpoints `/config` et
   `/create-checkout-session` :
   ```bash
   python server.py
   ```
5. Ouvrez `http://localhost:5000/pricing.html` (ou toute autre variante de langue) et cliquez sur
   un bouton d'essai pour rediriger vers Stripe Checkout.

> ⚠️ Les clés secrètes Stripe doivent rester côté serveur. Ne les commitez jamais dans le dépôt.

### Fournir la clé Stripe côté client (hébergement purement statique)

Si vous hébergez uniquement les fichiers statiques sans serveur (ex.: S3, GitHub Pages) et ne
disposez pas d'un endpoint `/config`, vous pouvez exposer la clé publique directement dans la page.
Le script `assets/js/stripe-checkout.js` détecte automatiquement plusieurs emplacements :

- un attribut `data-stripe-publishable-key` sur `<html>` ou `<body>` ;
- une balise `<meta name="stripe-publishable-key" content="pk_live_xxx">` ;
- un bloc `<script data-stripe-config data-publishable-key="pk_test_xxx"></script>` ;
- un objet global `window.__ENV__`, `window.__config` ou `window.__stripeConfig` contenant
  `publishableKey` ou `STRIPE_PUBLISHABLE_KEY` ;
- une variable globale `window.STRIPE_PUBLISHABLE_KEY`, `window.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`,
  `window.STRIPE_PUBLIC_KEY`, `window.stripePublishableKey` ou `window.econodealStripePublishableKey`.

Veillez à n'utiliser qu'une clé **publishable** (publique). Les clés secrètes doivent rester côté
serveur.

© 2025 EconoDeal
