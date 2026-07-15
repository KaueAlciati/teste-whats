from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from tqdm import tqdm
import time

# Configuração do navegador
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--log-level=3")
options.add_experimental_option("excludeSwitches", ["enable-logging"])

# Inicializa o navegador
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# Acessa o site
driver.get("https://www.fundsexplorer.com.br/funds")

# Aguarda a primeira letra aparecer
WebDriverWait(driver, 15).until(
    EC.presence_of_element_located((By.XPATH, '//*[@id="letter-id-A"]/div[1]/div[1]/a/div'))
)
time.sleep(2)

# Percorrer todas as letras de A a Z
letras = [chr(c) for c in range(ord('A'), ord('Z') + 1)]
dados = []

for letra in tqdm(letras, desc="🔎 Raspando FIIs"):
    i = 1
    while True:
        try:
            nome_xpath = f'//*[@id="letter-id-{letra}"]/div[1]/div[{i}]/a/div'
            segmento_xpath = f'//*[@id="letter-id-{letra}"]/div[1]/div[{i}]/span'

            nome_element = driver.find_element(By.XPATH, nome_xpath)
            segmento_element = driver.find_element(By.XPATH, segmento_xpath)

            nome = nome_element.get_attribute("innerText").strip()
            segmento = segmento_element.get_attribute("innerText").strip()

            dados.append({"ticker": nome, "segmento": segmento})
            i += 1
        except:
            break

driver.quit()

# Salva CSV
df = pd.DataFrame(dados)
csv_path = "E:/whatsapp_gastos_ai/backend/data/lista_fiis_fundsexplorer_completa.csv"
df.to_csv(csv_path, index=False, encoding="utf-8-sig")

print(f"\n✅ Raspagem completa! {len(df)} FIIs salvos.")
print(f"📁 Arquivo salvo em: {csv_path}")