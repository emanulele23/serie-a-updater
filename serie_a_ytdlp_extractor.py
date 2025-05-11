#!/usr/bin/env python3
"""
Estrattore di Stream Serie A - Approccio simile a m3u8downloader
---------------------------------------------------------------
Questo script utilizza tecniche simili al progetto m3u8downloader per
estrarre gli URL degli stream M3U8 per le partite di Serie A.
"""

import requests
from bs4 import BeautifulSoup
import re
import logging
import time
from datetime import datetime

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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': URL_BASE,
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}

def get_page_content(url, headers=None, session=None):
    """Scarica il contenuto della pagina specificata."""
    try:
        if headers is None:
            headers = HEADERS
        
        if session is None:
            session = requests.Session()
            
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text, session
    except Exception as e:
        logger.error(f"Errore nel download della pagina {url}: {e}")
        return None, session

def extract_m3u8_urls(html_content):
    """Estrae URL M3U8 dal contenuto HTML usando un approccio simile a m3u8downloader."""
    # Pattern per trovare URL M3U8
    m3u8_pattern = r'(https?://[^"\'\s<>]+\.m3u8(?:[^"\'\s<>])*)'
    matches = re.findall(m3u8_pattern, html_content)
    
    # Pulisci gli URL (rimuovi caratteri di escape e parametri duplicati)
    clean_urls = []
    for url in matches:
        # Rimuovi escape per caratteri speciali
        url = url.replace('\\/', '/').replace('\\&', '&').replace('\\=', '=')
        
        # A volte ci sono caratteri di terminazione come ) o } alla fine dell'URL
        url = re.sub(r'[)\]}]$', '', url)
        
        clean_urls.append(url)
    
    # Filtra per URL autenticati
    auth_urls = [url for url in clean_urls if "md5=" in url or "token=" in url or "auth=" in url or "expiretime=" in url]
    
    if auth_urls:
        logger.info(f"Trovati {len(auth_urls)} URL M3U8 autenticati")
        return auth_urls
    
    logger.info(f"Trovati {len(clean_urls)} URL M3U8 non autenticati")
    return clean_urls

def extract_iframe_urls(html_content, base_url):
    """Estrae gli URL degli iframe dal contenuto HTML."""
    iframe_urls = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src')
        if src:
            # Normalizza l'URL
            if src.startswith('//'):
                src = 'https:' + src
            elif not src.startswith('http'):
                src = base_url + ('/' if not base_url.endswith('/') and not src.startswith('/') else '') + src.lstrip('/')
            
            iframe_urls.append(src)
    
    logger.info(f"Trovati {len(iframe_urls)} iframe")
    return iframe_urls

def scan_for_m3u8_in_iframes(iframe_urls, base_url, session):
    """Esegue la scansione degli iframe alla ricerca di URL M3U8."""
    all_m3u8_urls = []
    
    for iframe_url in iframe_urls:
        try:
            logger.info(f"Scansione iframe: {iframe_url}")
            
            # Ottieni il contenuto dell'iframe
            iframe_content, session = get_page_content(
                iframe_url, 
                headers={**HEADERS, 'Referer': base_url},
                session=session
            )
            
            if iframe_content:
                # Cerca URL M3U8 nell'iframe
                iframe_m3u8_urls = extract_m3u8_urls(iframe_content)
                all_m3u8_urls.extend(iframe_m3u8_urls)
                
                # Cerca iframe annidati
                nested_iframes = extract_iframe_urls(iframe_content, iframe_url)
                if nested_iframes:
                    nested_m3u8_urls = scan_for_m3u8_in_iframes(nested_iframes, iframe_url, session)
                    all_m3u8_urls.extend(nested_m3u8_urls)
        except Exception as e:
            logger.error(f"Errore nella scansione dell'iframe {iframe_url}: {e}")
    
    return all_m3u8_urls

def check_url_accessibility(url, headers=None, session=None):
    """Verifica se un URL è accessibile."""
    if headers is None:
        headers = HEADERS
    
    if session is None:
        session = requests.Session()
        
    try:
        response = session.head(url, headers=headers, timeout=5)
        return response.status_code < 400
    except:
        try:
            # Alcuni server non supportano HEAD, prova con GET
            response = session.get(url, headers=headers, timeout=5, stream=True)
            response.close()  # Chiudi la connessione subito
            return response.status_code < 400
        except:
            return False

def prioritize_m3u8_urls(m3u8_urls, title):
    """Dà priorità agli URL M3U8 in base a criteri specifici."""
    if not m3u8_urls:
        return None
    
    # Filtra e ordina per priorità
    
    # 1. Prima priorità: URL con parametri di autenticazione
    auth_urls = [url for url in m3u8_urls if "md5=" in url and "expiretime=" in url]
    if auth_urls:
        logger.info(f"Uso URL autenticato con md5 e expiretime")
        return auth_urls[0]
    
    # 2. Seconda priorità: URL con qualsiasi parametro di autenticazione
    other_auth_urls = [url for url in m3u8_urls if "token=" in url or "auth=" in url or "key=" in url]
    if other_auth_urls:
        logger.info(f"Uso URL autenticato con altri parametri")
        return other_auth_urls[0]
    
    # 3. Terza priorità: URL da domini conosciuti per lo streaming
    known_domain_urls = [url for url in m3u8_urls if any(domain in url for domain in ["eachna.fun", "etrhg.fun"])]
    if known_domain_urls:
        logger.info(f"Uso URL da dominio conosciuto")
        return known_domain_urls[0]
    
    # 4. Ultima priorità: altri URL, evitando quelli generici noti
    filtered_urls = [url for url in m3u8_urls if "hls.kangal.icu/hls/serie/index.m3u8" not in url]
    if filtered_urls:
        logger.info(f"Uso URL generico filtrato")
        return filtered_urls[0]
    
    # Se non c'è altro, usa il primo URL disponibile
    logger.info(f"Uso primo URL disponibile")
    return m3u8_urls[0]

def extract_stream_url(match_url, title):
    """Estrae l'URL dello stream dalla pagina della partita usando l'approccio m3u8downloader."""
    logger.info(f"Estrazione URL da: {match_url}")
    
    # Crea una sessione per mantenere i cookie
    session = requests.Session()
    
    # Ottieni il contenuto della pagina principale
    html_content, session = get_page_content(match_url, session=session)
    if not html_content:
        return None
    
    # Lista per memorizzare tutti gli URL M3U8 trovati
    all_m3u8_urls = []
    
    # 1. Cerca URL M3U8 nella pagina principale
    page_m3u8_urls = extract_m3u8_urls(html_content)
    all_m3u8_urls.extend(page_m3u8_urls)
    
    # 2. Estrai iframe
    iframe_urls = extract_iframe_urls(html_content, match_url)
    
    # 3. Scansiona iframe
    iframe_m3u8_urls = scan_for_m3u8_in_iframes(iframe_urls, match_url, session)
    all_m3u8_urls.extend(iframe_m3u8_urls)
    
    # 4. Rimuovi duplicati
    unique_m3u8_urls = list(set(all_m3u8_urls))
    logger.info(f"Trovati {len(unique_m3u8_urls)} URL M3U8 unici")
    
    # 5. Verifica l'accessibilità degli URL
    accessible_urls = []
    for url in unique_m3u8_urls:
        if check_url_accessibility(url, session=session):
            logger.info(f"URL accessibile: {url}")
            accessible_urls.append(url)
        else:
            logger.info(f"URL non accessibile: {url}")
    
    if accessible_urls:
        # 6. Dà priorità agli URL accessibili
        return prioritize_m3u8_urls(accessible_urls, title)
    else:
        # Se nessun URL è accessibile, prova comunque con la prioritizzazione standard
        return prioritize_m3u8_urls(unique_m3u8_urls, title)

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
    content, _ = get_page_content(URL_LISTA)
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
            
            # Estrai URL dello stream
            stream_url = extract_stream_url(match_url, title)
            
            if stream_url:
                partite_trovate.append((title, stream_url))
            else:
                logger.warning(f"Impossibile trovare URL per: {title}")
    
    # Crea il file M3U8
    if create_m3u8_file(partite_trovate):
        logger.info(f"Aggiornamento completato: {len(partite_trovate)} partite di Serie A aggiunte")
    else:
        logger.warning("Aggiornamento non riuscito")

if __name__ == "__main__":
    main()
