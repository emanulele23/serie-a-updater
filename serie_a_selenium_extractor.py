#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
import logging
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("serie_a_updater.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Configurazione
URL_BASE = "https://calcio.beer"
URL_LISTA = f"{URL_BASE}/streaming-gratis-calcio-1.php"
OUTPUT_FILE = "serie_a.m3u8"
SEARCH_TERM = "Serie A"  # Termine da cercare negli h6

# Headers comuni per simulare un browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': URL_BASE,
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}

def get_page_content(url):
    """Scarica il contenuto della pagina specificata."""
    try:
        headers = HEADERS
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Errore nel download della pagina {url}: {e}")
        return None

def setup_selenium_driver():
    """Configura e restituisce un driver Selenium."""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Esecuzione headless (senza UI)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
        
        # La service può non essere necessaria con le versioni più recenti di Selenium
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)  # Timeout di 60 secondi per il caricamento della pagina
        
        # Configura una funzione di cattura del log di rete (DevTools)
        driver.execute_cdp_cmd("Network.enable", {})
        
        return driver
    except Exception as e:
        logger.error(f"Errore nella configurazione di Selenium: {e}")
        return None

def extract_m3u8_url_with_selenium(url):
    """
    Estrae gli URL M3U8 dalla pagina usando Selenium per intercettare le richieste di rete,
    simulando ciò che fa l'estensione Video DownloadHelper.
    """
    driver = None
    try:
        logger.info(f"Inizializzazione di Selenium per l'URL: {url}")
        driver = setup_selenium_driver()
        if not driver:
            raise Exception("Impossibile inizializzare il driver Selenium")
        
        # Lista per memorizzare tutte le richieste di rete
        m3u8_urls = []
        
        # Funzione di callback per monitorare le richieste di rete
        def log_request(request):
            if request.get('url') and '.m3u8' in request.get('url'):
                logger.info(f"Rilevato URL M3U8: {request.get('url')}")
                m3u8_urls.append(request.get('url'))
        
        # Registra la funzione di callback per monitorare le richieste
        driver.execute_cdp_cmd("Network.setRequestInterception", {"patterns": [{"urlPattern": "*"}]})
        driver.on_request = log_request
        
        # Carica la pagina
        logger.info(f"Caricamento della pagina: {url}")
        driver.get(url)
        
        # Attendi che la pagina sia completamente caricata
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Dai tempo agli script di essere eseguiti e al video di iniziare a caricarsi
        time.sleep(10)  # Attendi 10 secondi per il caricamento dei media
        
        # Se non abbiamo URL M3U8 dalle richieste, cerchiamo di fare clic su pulsanti di play o elementi video
        if not m3u8_urls:
            logger.info("Cercando elementi video e pulsanti di play...")
            
            # Cerca iframe e passa ad essi
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i, iframe in enumerate(iframes):
                try:
                    logger.info(f"Passaggio all'iframe {i+1}/{len(iframes)}")
                    driver.switch_to.frame(iframe)
                    
                    # Cerca pulsanti di play nell'iframe
                    play_buttons = driver.find_elements(By.CSS_SELECTOR, ".play-button, .vjs-big-play-button, [class*='play'], button")
                    for button in play_buttons:
                        try:
                            logger.info("Tentativo di clic su pulsante di play")
                            driver.execute_script("arguments[0].click();", button)
                            time.sleep(3)  # Attendi dopo il clic
                        except:
                            pass
                    
                    # Torna al contesto principale
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()
                    continue
            
            # Attendi altri 5 secondi per dare tempo alle nuove richieste di rete
            time.sleep(5)
        
        # Recupera tutte le richieste di rete catturate
        logs = driver.execute_cdp_cmd("Network.getResponseBody", {})
        for log_entry in logs:
            if '.m3u8' in log_entry.get('url', ''):
                m3u8_urls.append(log_entry.get('url'))
        
        # Cerca anche nel codice HTML della pagina e degli iframe
        page_source = driver.page_source
        m3u8_matches = re.findall(r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)', page_source)
        m3u8_urls.extend(m3u8_matches)
        
        # Rimuovi duplicati
        m3u8_urls = list(set(m3u8_urls))
        
        if m3u8_urls:
            logger.info(f"Trovati {len(m3u8_urls)} URL M3U8: {m3u8_urls}")
            # Restituisci il primo URL M3U8 valido
            return m3u8_urls[0]
        else:
            logger.warning(f"Nessun URL M3U8 trovato per: {url}")
            return None
            
    except Exception as e:
        logger.error(f"Errore nell'estrazione dell'URL M3U8 con Selenium: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def extract_m3u8_url_regex(url):
    """
    Metodo di fallback: estrae l'URL M3U8 cercando pattern nel codice HTML
    da usare se Selenium fallisce o non è disponibile.
    """
    try:
        logger.info(f"Tentativo di estrazione con regex da: {url}")
        content = get_page_content(url)
        if not content:
            return None
            
        # Cerca tutti i possibili URL M3U8
        m3u8_pattern = r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)'
        matches = re.findall(m3u8_pattern, content)
        
        if matches:
            logger.info(f"URL M3U8 trovati con regex: {matches}")
            return matches[0]  # Restituisci il primo match
        
        logger.warning(f"Nessun URL M3U8 trovato con regex in: {url}")
        return None
    except Exception as e:
        logger.error(f"Errore nell'estrazione con regex: {e}")
        return None

def create_m3u8_file(matches):
    """Crea il file M3U8 con le partite trovate."""
    try:
        if not matches:
            logger.warning("Nessuna partita di Serie A trovata per aggiornare il file M3U8")
            return False
            
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # Intestazione file M3U8
            f.write("#EXTM3U\n")
            
            # Aggiungi ogni partita
            for title, stream_url in matches:
                # Pulizia e formattazione del titolo
                clean_title = title.strip()
                # Aggiungi data attuale al titolo
                today = datetime.now().strftime("%d/%m")
                # Scrivi nel file
                f.write(f'#EXTINF:-1,{today} - {clean_title}\n')
                f.write(f'{stream_url}\n')
                
        logger.info(f"File M3U8 creato con successo: {OUTPUT_FILE} con {len(matches)} partite")
        return True
    except Exception as e:
        logger.error(f"Errore nella creazione del file M3U8: {e}")
        return False

def main():
    logger.info("Inizio aggiornamento lista Serie A")
    
    # Ottieni la lista delle partite
    content = get_page_content(URL_LISTA)
    if not content:
        logger.error("Impossibile ottenere la lista delle partite")
        return
    
    # Analizza il contenuto HTML
    soup = BeautifulSoup(content, 'html.parser')
    
    # Cerca elementi li che contengono partite
    partite_trovate = []
    match_items = soup.find_all('li')
    
    for item in match_items:
        # Trova l'elemento h6 e controlla se contiene "Serie A"
        h6_element = item.select_one('.kode_ticket_text h6')
        if h6_element and SEARCH_TERM.lower() in h6_element.text.lower():
            # Estrai il titolo (primo h2)
            title_element = item.select_one('.ticket_title h2')
            if not title_element:
                continue
                
            title = title_element.text.strip()
            
            # Estrai il link "Guarda Gratis"
            link_element = item.select_one('.ticket_btn a')
            if not link_element or not link_element.get('href'):
                continue
                
            match_url = link_element['href']
            if not match_url.startswith('http'):
                match_url = URL_BASE + match_url
            
            logger.info(f"Partita Serie A trovata: {title}, URL: {match_url}")
            
            # Aggiungi un piccolo delay per non sovraccaricare il server
            time.sleep(2)
            
            # Prova prima con Selenium
            try:
                stream_url = extract_m3u8_url_with_selenium(match_url)
            except Exception as e:
                logger.error(f"Errore con Selenium, passaggio a regex: {e}")
                stream_url = None
                
            # Se Selenium fallisce, usa il metodo regex
            if not stream_url:
                stream_url = extract_m3u8_url_regex(match_url)
            
            if stream_url:
                partite_trovate.append((title, stream_url))
    
    # Crea il file M3U8
    if create_m3u8_file(partite_trovate):
        logger.info(f"Aggiornamento completato: {len(partite_trovate)} partite di Serie A aggiunte")
    else:
        logger.warning("Aggiornamento non riuscito")

if __name__ == "__main__":
    main()
