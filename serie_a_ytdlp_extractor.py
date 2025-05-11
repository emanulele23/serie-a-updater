#!/usr/bin/env python3
"""
Estrattore di Stream Serie A - Usando m3u8 parser
------------------------------------------------
Questo script utilizza la libreria m3u8 di Globo.com per analizzare
ed estrarre gli URL degli stream M3U8 per le partite di Serie A.
"""

import requests
from bs4 import BeautifulSoup
import re
import logging
import time
import m3u8
from urllib.parse import urljoin
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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': URL_BASE,
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}

def get_page_content(url, headers=None):
    """Scarica il contenuto della pagina specificata."""
    try:
        if headers is None:
            headers = HEADERS
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Errore nel download della pagina {url}: {e}")
        return None

def find_iframes(html_content, base_url):
    """Trova tutti gli iframe nella pagina."""
    iframe_urls = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src')
        if src:
            # Normalizza l'URL
            if src.startswith('//'):
                src = 'https:' + src
            elif not src.startswith('http'):
                src = urljoin(base_url, src)
            
            iframe_urls.append(src)
    
    return iframe_urls

def find_m3u8_urls(html_content):
    """Trova tutti gli URL M3U8 nella pagina."""
    # Pattern ampio per catturare URL M3U8
    m3u8_pattern = r'(https?://[^"\'\s<>)]+\.m3u8(?:[^"\'\s<>),]*)?)'
    matches = re.findall(m3u8_pattern, html_content)
    
    # Pulisci gli URL
    clean_urls = []
    for url in matches:
        # Rimuovi escape per caratteri speciali
        url = url.replace('\\/', '/').replace('\\&', '&').replace('\\=', '=')
        # A volte ci sono caratteri di terminazione come ) o } alla fine dell'URL
        url = re.sub(r'[)\]}]$', '', url)
        clean_urls.append(url)
    
    return clean_urls

def validate_m3u8_url(url):
    """Verifica se un URL M3U8 è valido usando la libreria m3u8."""
    try:
        # Imposta un timeout più breve per questa richiesta
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        # Prova a parsare l'M3U8
        parsed_m3u8 = m3u8.loads(response.text)
        
        # Controlla se è un master playlist o media playlist
        if parsed_m3u8.is_variant:
            # È un master playlist, controlla se ci sono playlists
            if parsed_m3u8.playlists:
                logger.info(f"URL valido (master playlist con {len(parsed_m3u8.playlists)} varianti): {url}")
                return True
        elif parsed_m3u8.segments:
            # È un media playlist, controlla se ci sono segmenti
            logger.info(f"URL valido (media playlist con {len(parsed_m3u8.segments)} segmenti): {url}")
            return True
        
        logger.warning(f"URL M3U8 non valido (nessun segmento/playlist): {url}")
        return False
    except Exception as e:
        logger.warning(f"URL M3U8 non valido: {url} - Errore: {e}")
        return False

def get_best_url(m3u8_urls):
    """Seleziona il miglior URL M3U8 dalla lista."""
    if not m3u8_urls:
        return None
    
    # Verifica quali URL sono validi
    valid_urls = []
    for url in m3u8_urls:
        if validate_m3u8_url(url):
            valid_urls.append(url)
    
    if not valid_urls:
        logger.warning("Nessun URL M3U8 valido trovato")
        return None
    
    # Dai priorità agli URL con parametri di autenticazione
    auth_urls = [url for url in valid_urls if "md5=" in url or "token=" in url]
    if auth_urls:
        logger.info(f"Selezionato URL autenticato: {auth_urls[0]}")
        return auth_urls[0]
    
    # Filtra per evitare URL generici noti
    non_generic_urls = [url for url in valid_urls if "kangal.icu/hls/serie/index.m3u8" not in url]
    if non_generic_urls:
        logger.info(f"Selezionato URL non generico: {non_generic_urls[0]}")
        return non_generic_urls[0]
    
    # Se tutto fallisce, restituisci il primo URL valido
    logger.info(f"Selezionato primo URL valido: {valid_urls[0]}")
    return valid_urls[0]

def extract_stream_url(match_url):
    """Estrae l'URL dello stream dalla pagina della partita."""
    logger.info(f"Estrazione URL da: {match_url}")
    
    # Ottieni il contenuto della pagina principale
    html_content = get_page_content(match_url)
    if not html_content:
        return None
    
    # Trova tutti gli URL M3U8 nella pagina principale
    m3u8_urls = find_m3u8_urls(html_content)
    logger.info(f"Trovati {len(m3u8_urls)} URL M3U8 nella pagina principale")
    
    # Trova tutti gli iframe
    iframe_urls = find_iframes(html_content, match_url)
    logger.info(f"Trovati {len(iframe_urls)} iframe")
    
    # Controlla gli iframe per URL M3U8 aggiuntivi
    for iframe_url in iframe_urls:
        try:
            iframe_content = get_page_content(iframe_url, headers={**HEADERS, 'Referer': match_url})
            if iframe_content:
                iframe_m3u8_urls = find_m3u8_urls(iframe_content)
                logger.info(f"Trovati {len(iframe_m3u8_urls)} URL M3U8 nell'iframe {iframe_url}")
                m3u8_urls.extend(iframe_m3u8_urls)
                
                # Cerca iframe annidati
                nested_iframes = find_iframes(iframe_content, iframe_url)
                for nested_iframe in nested_iframes:
                    try:
                        nested_content = get_page_content(nested_iframe, headers={**HEADERS, 'Referer': iframe_url})
                        if nested_content:
                            nested_m3u8_urls = find_m3u8_urls(nested_content)
                            logger.info(f"Trovati {len(nested_m3u8_urls)} URL M3U8 nell'iframe annidato {nested_iframe}")
                            m3u8_urls.extend(nested_m3u8_urls)
                    except Exception as e:
                        logger.error(f"Errore nell'analisi dell'iframe annidato {nested_iframe}: {e}")
        except Exception as e:
            logger.error(f"Errore nell'analisi dell'iframe {iframe_url}: {e}")
    
    # Rimuovi duplicati
    unique_m3u8_urls = list(set(m3u8_urls))
    logger.info(f"Trovati {len(unique_m3u8_urls)} URL M3U8 unici in totale")
    
    # Seleziona il miglior URL
    best_url = get_best_url(unique_m3u8_urls)
    if best_url:
        logger.info(f"URL migliore selezionato: {best_url}")
    else:
        logger.warning("Nessun URL M3U8 valido trovato")
    
    return best_url

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
            
            # Estrai URL dello stream
            stream_url = extract_stream_url(match_url)
            
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
