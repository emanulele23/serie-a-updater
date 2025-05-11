#!/usr/bin/env python3
"""
Estrattore di Stream Serie A
-----------------------------
Questo script estrae gli URL degli stream M3U8 per le partite di Serie A
utilizzando tecniche avanzate di estrazione simili a Video DownloadHelper.
Autore: Claude
Data: Maggio 2025
"""

import requests
from bs4 import BeautifulSoup
import re
import logging
import time
import subprocess
import json
from datetime import datetime
import random

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

# Lista di User-Agent per rotazione
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
]

def get_random_ua():
    """Restituisce un User-Agent casuale dalla lista."""
    return random.choice(USER_AGENTS)

def get_headers(referer=None):
    """Genera headers con User-Agent casuale e referer opzionale."""
    headers = {
        'User-Agent': get_random_ua(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    if referer:
        headers['Referer'] = referer
        
    return headers

def get_page_content(url, referer=None, allow_redirects=True):
    """Scarica il contenuto della pagina specificata."""
    try:
        headers = get_headers(referer)
        session = requests.Session()
        
        # Aggiungi un piccolo delay per simulare comportamento umano
        time.sleep(random.uniform(0.5, 1.5))
        
        response = session.get(url, headers=headers, timeout=30, allow_redirects=allow_redirects)
        response.raise_for_status()
        
        final_url = response.url
        if allow_redirects and final_url != url:
            logger.info(f"Reindirizzato da {url} a {final_url}")
            
        return response.text, session, final_url
    except Exception as e:
        logger.error(f"Errore nel download della pagina {url}: {e}")
        return None, None, None

def extract_iframe_urls(html_content, base_url):
    """Estrae gli URL degli iframe dal contenuto HTML."""
    iframe_urls = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src')
        if src:
            # Normalizza l'URL
            if src.startswith('//'):
                src = 'https:' + src
            elif not src.startswith('http'):
                src = base_url + ('/' if not base_url.endswith('/') and not src.startswith('/') else '') + src.lstrip('/')
            
            iframe_urls.append(src)
            logger.info(f"Trovato iframe: {src}")
            
    return iframe_urls

def extract_m3u8_from_javascript(js_content):
    """Estrae URL M3U8 da contenuto JavaScript."""
    m3u8_urls = []
    
    # Pattern per variabili JavaScript che potrebbero contenere URL M3U8
    js_patterns = [
        r'var\s+\w+\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    ]
    
    for pattern in js_patterns:
        matches = re.findall(pattern, js_content)
        for match in matches:
            if '.m3u8' in match:
                # Assicurati che sia un URL completo
                if match.startswith('//'):
                    match = 'https:' + match
                elif not match.startswith('http'):
                    continue
                
                m3u8_urls.append(match)
                
    return m3u8_urls

def extract_m3u8_direct(html_content):
    """Estrae URL M3U8 direttamente dal contenuto HTML."""
    # Pattern per URL M3U8
    m3u8_pattern = r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)'
    matches = re.findall(m3u8_pattern, html_content)
    
    return matches

def extract_access_tokens(html_content):
    """Estrae token di accesso o parametri di autenticazione che potrebbero essere usati per costruire URL."""
    tokens = {}
    
    # Pattern per token MD5
    md5_pattern = r'md5\s*[:=]\s*["\']([^"\']+)["\']'
    md5_matches = re.findall(md5_pattern, html_content)
    if md5_matches:
        tokens['md5'] = md5_matches[0]
    
    # Pattern per token di scadenza
    expire_pattern = r'expiretime\s*[:=]\s*["\']?(\d+)["\']?'
    expire_matches = re.findall(expire_pattern, html_content)
    if expire_matches:
        tokens['expiretime'] = expire_matches[0]
    
    # Pattern per altri token comuni
    token_pattern = r'token\s*[:=]\s*["\']([^"\']+)["\']'
    token_matches = re.findall(token_pattern, html_content)
    if token_matches:
        tokens['token'] = token_matches[0]
    
    return tokens

def deep_scan_iframe(iframe_url, parent_url):
    """Analizza in profondità un iframe per trovare URL M3U8."""
    logger.info(f"Analisi profonda dell'iframe: {iframe_url}")
    
    html_content, session, final_url = get_page_content(iframe_url, referer=parent_url)
    if not html_content:
        return []
    
    # Lista per memorizzare tutti gli URL M3U8 trovati
    all_m3u8_urls = []
    
    # 1. Cerca URL M3U8 diretti nell'HTML
    direct_urls = extract_m3u8_direct(html_content)
    all_m3u8_urls.extend(direct_urls)
    
    # 2. Cerca URL in JavaScript
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')
    
    for script in scripts:
        script_content = script.string
        if not script_content:
            continue
            
        js_urls = extract_m3u8_from_javascript(script_content)
        all_m3u8_urls.extend(js_urls)
    
    # 3. Cerca iframe annidati
    nested_iframes = extract_iframe_urls(html_content, iframe_url)
    
    for nested_url in nested_iframes:
        if nested_url != iframe_url:  # Evita loop infiniti
            nested_urls = deep_scan_iframe(nested_url, iframe_url)
            all_m3u8_urls.extend(nested_urls)
    
    # 4. Cerca token di accesso
    tokens = extract_access_tokens(html_content)
    
    # Se abbiamo trovato token di accesso, possiamo provare a costruire URL completi
    if tokens and 'md5' in tokens and 'expiretime' in tokens:
        # Pattern comuni di base URL per stream con autenticazione
        base_domains = [
            "duko.eachna.fun",
            "liauth.etrhg.fun",
            "hls.kangal.icu"
        ]
        
        # Cerca riferimenti a path negli script
        path_pattern = r'path\s*[:=]\s*["\']([^"\']+)["\']'
        path_matches = re.findall(path_pattern, html_content)
        
        stream_name_pattern = r'(juve\d+|inter\d+|milan\d+|napoli\d+|roma\d+|lazio\d+)'
        stream_matches = re.findall(stream_name_pattern, html_content)
        
        paths = []
        if path_matches:
            paths.extend(path_matches)
        if stream_matches:
            paths.extend([f"hls/{match}/index.m3u8" for match in stream_matches])
        
        # Aggiungi alcuni path comuni
        if not paths:
            paths = ["hls/serie/index.m3u8", "hls/stream/index.m3u8", "index.m3u8"]
        
        # Costruisci URL potenziali
        for domain in base_domains:
            for path in paths:
                url = f"https://{domain}/{path}?md5={tokens['md5']}&expiretime={tokens['expiretime']}"
                all_m3u8_urls.append(url)
    
    # Rimuovi duplicati
    return list(set(all_m3u8_urls))

def advanced_m3u8_extraction(url):
    """
    Estrattore avanzato di URL M3U8 che usa tecniche multiple.
    Simula il comportamento di Video DownloadHelper.
    """
    try:
        logger.info(f"Estrazione avanzata da: {url}")
        
        # 1. Ottieni il contenuto della pagina principale
        html_content, session, final_url = get_page_content(url)
        if not html_content:
            return None
        
        # 2. Lista per memorizzare tutti gli URL M3U8 trovati
        all_m3u8_urls = []
        
        # 3. Cerca URL M3U8 diretti
        direct_urls = extract_m3u8_direct(html_content)
        all_m3u8_urls.extend(direct_urls)
        
        # 4. Cerca URL in JavaScript
        soup = BeautifulSoup(html_content, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            script_content = script.string
            if not script_content:
                continue
                
            js_urls = extract_m3u8_from_javascript(script_content)
            all_m3u8_urls.extend(js_urls)
        
        # 5. Cerca iframe e analizzali in profondità
        iframe_urls = extract_iframe_urls(html_content, final_url)
        
        for iframe_url in iframe_urls:
            iframe_m3u8_urls = deep_scan_iframe(iframe_url, final_url)
            all_m3u8_urls.extend(iframe_m3u8_urls)
        
        # 6. Rimuovi duplicati
        unique_urls = list(set(all_m3u8_urls))
        
        # 7. Filtra per priorità
        # Priorità a URL con parametri di autenticazione
        auth_urls = [u for u in unique_urls if "md5=" in u and "expiretime=" in u]
        if auth_urls:
            logger.info(f"Trovati {len(auth_urls)} URL M3U8 autenticati: {auth_urls[0]}")
            return auth_urls[0]  # Restituisci il primo URL autenticato
            
        token_urls = [u for u in unique_urls if "token=" in u or "auth=" in u or "key=" in u]
        if token_urls:
            logger.info(f"Trovati {len(token_urls)} URL M3U8 con token: {token_urls[0]}")
            return token_urls[0]  # Restituisci il primo URL con token
            
        # Se non ci sono URL autenticati, restituisci un URL generico
        if unique_urls:
            # Evita gli URL generici conosciuti
            filtered_urls = [u for u in unique_urls if "hls.kangal.icu/hls/serie/index.m3u8" not in u]
            if filtered_urls:
                logger.info(f"Trovati {len(filtered_urls)} URL M3U8 filtrati: {filtered_urls[0]}")
                return filtered_urls[0]
            else:
                logger.info(f"Trovati solo URL generici: {unique_urls[0]}")
                return unique_urls[0]
        
        logger.warning(f"Nessun URL M3U8 trovato per: {url}")
        return None
            
    except Exception as e:
        logger.error(f"Errore nell'estrazione avanzata: {e}")
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
    content, _, _ = get_page_content(URL_LISTA)
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
            
            # Usa l'estrattore avanzato
            stream_url = advanced_m3u8_extraction(match_url)
            
            # Prova con yt-dlp come backup
            if not stream_url:
                try:
                    logger.info(f"Estrattore avanzato fallito, tentativo con yt-dlp: {match_url}")
                    cmd = ["yt-dlp", "--print", "urls", "--no-warnings", match_url]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    urls = result.stdout.strip().split('\n')
                    
                    # Filtra per trovare URL M3U8
                    m3u8_urls = [u for u in urls if '.m3u8' in u]
                    if m3u8_urls:
                        stream_url = m3u8_urls[0]
                except Exception as e:
                    logger.error(f"Errore con yt-dlp: {e}")
            
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
