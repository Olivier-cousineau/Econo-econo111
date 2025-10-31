import requests

# URL cible et clé API Scrape.do
target_url = 'https://www.canadiantire.ca/fr/promotions/liquidation.html'
apikey = '79806d0a26a2413fb4a1c33f14dda9743940a7548ba'  # ta clé personnelle Scrape.do

response = requests.get(
    'https://api.scrape.do/',
    params={'url': target_url, 'key': apikey, 'country': 'CA'},
    timeout=60
)

if response.status_code == 200:
    html = response.text
    # Traite le html pour extraire tes liquidations >60%, comme dans le reste du script
else:
    print('Erreur Scrape.do:', response.content)
