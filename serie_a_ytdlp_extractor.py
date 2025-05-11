#!/usr/bin/env python3
"""
Estrattore di Stream Serie A
-----------------------------
Questo script estrae gli URL degli stream M3U8 per le partite di Serie A
utilizzando yt-dlp, uno strumento specializzato nell'estrazione di video.
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

def extract_m3u8_url_with_ytdlp(url):
    """
    Estrae l'URL M3U8 usando yt-dlp.
    yt-dlp è specializzato nell'estrazione di stream da vari siti.
    """
    try:
        logger.info(f"Estrazione URL M3U8 con yt-dlp da: {url}")
        
        # Comando yt-dlp per estrarre solo le informazioni dello stream
        # --dump-json: restituisce le informazioni in formato JSON
        # --no-playlist: evita di processare eventuali playlist
        # --no-warnings: riduce i messaggi di warning
        cmd = [
            "yt-dlp", 
            "--dump-json", 
            "--no-playlist",
            "--no-warnings",
            url
        ]
        
        # Esegui il comando
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if error:
            logger.warning(f"yt-dlp ha riportato errori: {error}")
        
        if not output:
            logger.warning(f"Nessun output da yt-dlp per: {url}")
            
            # Prova con --print urls per ottenere solo gli URL
            cmd_alt = ["yt-dlp", "--print", "urls", "--no-warnings", url]
            result_alt = subprocess.run(cmd_alt, capture_output=True, text=True)
            urls = result_alt.stdout.strip().split('\n')
            
            # Filtra per trovare URL M3U8
            m3u8_urls = [u for u in urls if '.m3u8' in u]
            if m3u8_urls:
                logger.info(f"Trovato URL M3U8 con yt-dlp (modalità urls): {m3u8_urls[0]}")
                return m3u8_urls[0]
                
            return None
            
        # Analizza l'output JSON
        try:
            info = json.loads(output)
            
            # Estrai URL dello stream
            if 'url' in info and '.m3u8' in info['url']:
                logger.info(f"Trovato URL M3U8 diretto in JSON: {info['url']}")
                return info['url']
                
            # Cerca nel campo formats
            if 'formats' in info:
                # Ordina per qualità, preferendo HLS (m3u8)
                hls_formats = [f for f in info['formats'] if '.m3u8' in f.get('url', '')]
                
                if hls_formats:
                    # Prendi l'URL del formato con la qualità migliore
                    best_url = hls_formats[-1]['url']
                    logger.info(f"Trovato URL M3U8 in formato: {best_url}")
                    return best_url
                    
            # Cerca nel campo manifest_url
            if 'manifest_url' in info and '.m3u8' in info['manifest_url']:
                logger.info(f"Trovato URL M3U8 in manifest_url: {info['manifest_url']}")
                return info['manifest_url']
                
            logger.warning(f"Nessun URL M3U8 trovato nel JSON di yt-dlp")
            
            # In alternativa, estrai direttamente gli URL
            cmd_alt = ["yt-dlp", "--print", "urls", "--no-warnings", url]
            result_alt = subprocess.run(cmd_alt, capture_output=True, text=True)
            urls = result_alt.stdout.strip().split('\n')
            
            # Filtra per trovare URL M3U8
            m3u8_urls = [u for u in urls if '.m3u8' in u]
            if m3u8_urls:
                logger.info(f"Trovato URL M3U8 con yt-dlp (modalità urls): {m3u8_urls[0]}")
                return m3u8_urls[0]
                
            return None
            
        except json.JSONDecodeError:
            logger.error(f"Impossibile decodificare il JSON da yt-dlp: {output}")
            
            # Se non è JSON, potrebbe essere un URL diretto
            if '.m3u8' in output:
                m3u8_urls = re.findall(r'(https?://[^"\'\s]+\.m3u8[^"\'\s,)]*)', output)
                if m3u8_urls:
                    logger.info(f"Trovato URL M3U8 nell'output: {m3u8_urls[0]}")
                    return m3u8_urls[0]
                    
            return None
            
    except Exception as e:
        logger.error(f"Errore nell'estrazione dell'URL M3U8 con yt-dlp: {e}")
        return None

def extract_m3u8_url_regex(url):
    """
    Metodo di fallback: estrae l'URL M3U8 cercando pattern nel codice HTML.
    Da usare se yt-dlp fallisce.
    """
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
            
            # Prova prima con yt-dlp
            stream_url = extract_m3u8_url_with_ytdlp(match_url)
                
            # Se yt-dlp fallisce, usa il metodo regex
            if not stream_url:
                logger.warning("yt-dlp fallito, tentativo con regex")
                stream_url = extract_m3u8_url_regex(match_url)
            
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
