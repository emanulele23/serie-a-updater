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
from webdriver_manager.chrome import ChromeDriverManager

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
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Usa webdriver_manager per gestire automaticamente il ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)  # Timeout di 60 secondi
        
        return driver
    except Exception as e:
        logger.error(f"Errore nella configurazione di Selenium: {e}")
        return None

def extract_network_requests(driver, url):
    """Estrae le richieste di rete tramite DevTools Protocol."""
    m3u8_urls = []
    
    def process_request(request):
        request_url = request.get('url', '')
        if '.m3u8' in request_url:
            logger.info(f"Intercettata richiesta M3U8: {request_url}")
            m3u8_urls.append(request_url)
    
    # Abilita il monitoraggio di rete
    driver.execute_cdp_cmd("Network.enable", {})
    
    # Imposta un listener per gli eventi di rete
    driver.on_request = process_request
    
    # Carica la pagina
    driver.get(url)
    
    # Attendi che la pagina sia caricata
    time.sleep(10)
    
    return m3u8_urls

def extract_m3u8_from_page_source(driver):
    """Estrae URL M3U8 dal codice sorgente della pagina."""
    m3u8_urls = []
    page_source = driver.page_source
    m3u8_matches = re.findall(r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)', page_source)
    
    # Filtra per URL autentici (con parametri di autenticazione)
    for url in m3u8_matches:
        if "md5=" in url or "token=" in url or "auth=" in url or "key=" in url or "expiretime=" in url:
            logger.info(f"Trovato URL M3U8 autentico: {url}")
            m3u8_urls.append(url)
        else:
            logger.info(f"Trovato URL M3U8 generico: {url}")
            m3u8_urls.append(url)
    
    return m3u8_urls

def interact_with_players(driver):
    """Interagisce con i player video per attivare lo streaming."""
    # Cerca elementi video
    try:
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        for video in video_elements:
            try:
                driver.execute_script("arguments[0].play();", video)
                logger.info("Avviata riproduzione video")
                time.sleep(3)
            except Exception as e:
                logger.error(f"Errore nell'interazione con video: {e}")
    except Exception as e:
        logger.error(f"Errore nella ricerca di elementi video: {e}")
    
    # Cerca pulsanti di play
    play_selectors = [
        ".play-button", 
        ".vjs-big-play-button", 
        "[class*='play']", 
        "button:contains('Play')", 
        ".jw-icon-playback",
        "[aria-label='Play']"
    ]
    
    for selector in play_selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, selector)
            for button in buttons:
                try:
                    driver.execute_script("arguments[0].click();", button)
                    logger.info(f"Cliccato pulsante play: {selector}")
                    time.sleep(3)
                except Exception as e:
                    logger.error(f"Errore nel cliccare pulsante: {e}")
        except:
            pass

def extract_m3u8_url_with_selenium(url):
    """Estrae URL M3U8 usando Selenium con varie tecniche."""
    driver = None
    try:
        logger.info(f"Avvio estrazione M3U8 con Selenium per: {url}")
        driver = setup_selenium_driver()
        if not driver:
            raise Exception("Impossibile inizializzare il driver Selenium")
        
        # Carica la pagina
        driver.get(url)
        logger.info(f"Pagina caricata: {url}")
        
        # Attendi che la pagina sia completamente caricata
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Estrai M3U8 dal codice sorgente
        direct_m3u8_urls = extract_m3u8_from_page_source(driver)
        
        # Interagisci con i player per attivare lo streaming
        interact_with_players(driver)
        
        # Attendi che i player si carichino
        time.sleep(5)
        
        # Estrai nuovamente dopo l'interazione
        post_interaction_urls = extract_m3u8_from_page_source(driver)
        
        # Gestisci iframe
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            logger.info(f"Trovati {len(iframes)} iframe")
            
            iframe_m3u8_urls = []
            for i, iframe in enumerate(iframes):
                try:
                    logger.info(f"Passaggio all'iframe {i+1}/{len(iframes)}")
                    driver.switch_to.frame(iframe)
                    
                    # Estrai M3U8 dall'iframe
                    iframe_urls = extract_m3u8_from_page_source(driver)
                    iframe_m3u8_urls.extend(iframe_urls)
                    
                    # Interagisci con i player nell'iframe
                    interact_with_players(driver)
                    
                    # Estrai nuovamente dopo l'interazione
                    iframe_post_urls = extract_m3u8_from_page_source(driver)
                    iframe_m3u8_urls.extend(iframe_post_urls)
                    
                    # Torna al contesto principale
                    driver.switch_to.default_content()
                except Exception as e:
                    logger.error(f"Errore nell'iframe {i+1}: {e}")
                    driver.switch_to.default_content()
            
            # Aggiungi URL degli iframe
            direct_m3u8_urls.extend(iframe_m3u8_urls)
            
        except Exception as e:
            logger.error(f"Errore nella gestione degli iframe: {e}")
        
        # Combina e deduplicizza
        all_urls = direct_m3u8_urls + post_interaction_urls
        unique_urls = list(set(all_urls))
        
        # Filtra per URL autentici (priorità ai link con parametri di autenticazione)
        auth_urls = [url for url in unique_urls if "md5=" in url or "token=" in url or "auth=" in url or "key=" in url or "expiretime=" in url]
        
        if auth_urls:
            logger.info(f"Trovati {len(auth_urls)} URL M3U8 autenticati")
            return auth_urls[0]  # Restituisci il primo URL autenticato
        elif unique_urls:
            logger.info(f"Trovati {len(unique_urls)} URL M3U8 generici")
            return unique_urls[0]  # Restituisci il primo URL generico se non ci sono URL autenticati
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
    """Metodo di fallback che usa regex per trovare URL M3U8."""
    try:
        logger.info(f"Tentativo di estrazione con regex da: {url}")
        content = get_page_content(url)
        if not content:
            return None
            
        # Cerca tutti i possibili URL M3U8
        m3u8_pattern = r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)'
        matches = re.findall(m3u8_pattern, content)
        
        # Filtra per URL autentici (priorità ai link con parametri di autenticazione)
        auth_matches = [url for url in matches if "md5=" in url or "token=" in url or "auth=" in url or "key=" in url or "expiretime=" in url]
        
        if auth_matches:
            logger.info(f"URL M3U8 autenticati trovati con regex: {auth_matches}")
            return auth_matches[0]  # Restituisci il primo URL autenticato
        elif matches:
            logger.info(f"URL M3U8 generici trovati con regex: {matches}")
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
