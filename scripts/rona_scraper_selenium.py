from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def scrape_rona_liquidation_selenium():
    url = "https://www.rona.ca/fr/promotions-store-41320-store-shopcart.qsf.store-inventory-available"

    # 🧱 Config Chrome headless
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # mode headless compatible Chrome 109+
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=fr-FR")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36"
    )

    # 🚗 Lance le navigateur
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        driver.get(url)

        # ✅ Attends l'apparition des produits
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "product-tile"))
        )

        # 📦 Récupère tous les produits
        products = driver.find_elements(By.CLASS_NAME, "product-tile")

        print(f"✅ {len(products)} produits trouvés\n")

        for p in products:
            try:
                title = p.find_element(By.CLASS_NAME, "product-tile__title").text
                price = p.find_element(By.CLASS_NAME, "price__value").text
                print(f"{title.strip()} - {price.strip()}")
            except Exception as e:
                print("[!] Produit partiellement lisible :", e)

    except Exception as e:
        print("❌ Erreur lors du scraping :", e)
    finally:
        driver.quit()


if __name__ == "__main__":
    scrape_rona_liquidation_selenium()
