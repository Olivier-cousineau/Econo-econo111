# Accorder l'accès Google Drive aux automatisations

Ce guide explique comment autoriser un script (ex. ceux du dossier `automation/`)
à récupérer automatiquement vos fichiers JSON stockés dans Google Drive et les
copier dans `incoming/` avant que le workflow GitHub n'organise les données.

## 1. Créer un projet et un compte de service
1. Ouvrez <https://console.cloud.google.com/> puis créez un projet dédié (ou
   choisissez-en un existant).
2. Dans **API & Services > Bibliothèque**, recherchez **Google Drive API** et
   cliquez sur **Activer**.
3. Rendez-vous dans **API & Services > Identifiants** puis cliquez sur
   **Créer des identifiants > Compte de service**.
4. Donnez un nom (ex. `econodeal-drive`), validez et créez le compte. Vous
   n'avez pas besoin de lui attribuer un rôle IAM particulier.
5. Ouvrez le compte de service nouvellement créé, onglet **Clés**, puis
   **Ajouter une clé > Créer une clé** de type **JSON**. Téléchargez le fichier
   `*.json` et placez-le hors du dépôt Git (ex. `/etc/econodeal/drive.json`).

## 2. Partager le dossier Drive cible
1. Dans l'interface web de Google Drive, faites un clic droit sur le dossier
   contenant vos exports JSON.
2. Choisissez **Partager** et invitez l'adresse e-mail du compte de service
   (format `xxx@xxx.iam.gserviceaccount.com`).
3. Donnez-lui un accès **Lecteur** ou **Contributeur** selon vos besoins.
4. Cliquez sur **Envoyer** pour finaliser le partage.

## 3. Installer les dépendances Python
Dans votre environnement virtuel (ex. `automation/.venv`) installez le SDK :

```bash
pip install google-api-python-client google-auth google-auth-httplib2
```

Ajoutez les paquets à `automation/requirements.txt` si vous souhaitez
redistribuer l'environnement.

## 4. Script de synchronisation minimal
Le snippet ci-dessous télécharge les fichiers JSON présents dans un dossier
Drive (identifié par son ID) et les copie vers `incoming/`.

```python
from __future__ import annotations

import io
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SERVICE_ACCOUNT_FILE = "/etc/econodeal/drive.json"  # chemin vers la clé
DRIVE_FOLDER_ID = "1AbCdEfGhIjKlMnOp"                # remplacez par votre ID
TARGET_DIR = Path("incoming")

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
)
service = build("drive", "v3", credentials=creds)

TARGET_DIR.mkdir(parents=True, exist_ok=True)

query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType = 'application/json'"
results = (
    service.files()
    .list(q=query, fields="files(id, name, modifiedTime)")
    .execute()
)

for item in results.get("files", []):
    request = service.files().get_media(fileId=item["id"])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        print(f"Téléchargement {item['name']}: {int(status.progress() * 100)}%")

    target_path = TARGET_DIR / item["name"]
    with open(target_path, "wb") as f:
        f.write(buffer.getvalue())

    print(f"Sauvegardé {target_path} (Drive: {item['modifiedTime']})")
```

> 💡 Identifiez l'ID du dossier via l'URL Drive : `https://drive.google.com/drive/folders/<ID>`.

Programmez l'exécution (cron, systemd timer, pipeline CI, etc.) puis laissez le
workflow GitHub manipuler les fichiers importés comme d'habitude.

## 5. Sécurité
- Conservez la clé JSON hors du dépôt et appliquez des permissions strictes
  (`chmod 600`).
- Limitez l'accès du compte de service aux seuls dossiers nécessaires.
- Révoquez la clé immédiatement en cas de fuite.

En suivant ces étapes, vos automatisations peuvent récupérer les fichiers Drive
sans exposer votre compte Google personnel.
