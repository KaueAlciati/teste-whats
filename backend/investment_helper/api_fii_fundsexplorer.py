from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time

def buscar_info_fii_funds_explorer(ticker: str):
    url = f"https://www.fundsexplorer.com.br/funds/{ticker.lower()}"

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # 👉 Usando Service corretamente
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    time.sleep(5)  # Aguarda o carregamento da página

    def safe_find(xpath):
        try:
            return driver.find_element(By.XPATH, xpath).text.strip()
        except:
            return "Não encontrado"

    info = {
        "nome": safe_find('//*[@id="carbon_fields_fiis_header-2"]/div/div/div[1]/p'),
        "preco_atual": safe_find('//*[@id="carbon_fields_fiis_header-2"]/div/div/div[1]/div[1]/p'),
        "variacao_dia": safe_find('//*[@id="carbon_fields_fiis_header-2"]/div/div/div[1]/div[1]/span'),
        "cnpj": safe_find('//*[@id="carbon_fields_fiis_header-2"]/div/div/div[1]/div[2]/b'),
        "liquidez_media": safe_find('//*[@id="indicators"]/div[1]/p[2]/b'),
        "ultimo_rendimento": safe_find('//*[@id="indicators"]/div[2]/p[2]/b'),
        "dividend_yield": safe_find('//*[@id="indicators"]/div[3]/p[2]/b'),
        "patrimonio_liquido": safe_find('//*[@id="indicators"]/div[4]/p[2]/b'),
        "valor_patrimonial": safe_find('//*[@id="indicators"]/div[5]/p[2]/b'),
        "rentabilidade_mes": safe_find('//*[@id="indicators"]/div[6]/p[2]/b'),
        "p_vp": safe_find('//*[@id="indicators"]/div[7]/p/b'),
        "numero_cotista": safe_find('//*[@id="carbon_fields_fiis_basic_informations-2"]/div/div/div[9]/p[2]/b')
    }

    driver.quit()
    return info

# Teste local
if __name__ == "__main__":
    resultado = buscar_info_fii_funds_explorer("MXRF11")
    print("🏢 Informações do FII via FundsExplorer:")
    for chave, valor in resultado.items():
        print(f"{chave.replace('_', ' ').capitalize()}: {valor}")