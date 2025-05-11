#!/usr/bin/env python3
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


def get_page_content(url):
    """Scarica il contenuto della pagina specificata."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Errore nel download della pagina {url}: {e}")
        return None


def extract_m3u8_url(page_url):
    """
    Estrae l'URL M3U8 dalla pagina di streaming.
    Cerca pattern conosciuti di URL M3U8 nel codice sorgente della pagina.
    """
    try:
        logger.info(f"Estrazione URL M3U8 da: {page_url}")

        # Ottieni il contenuto della pagina
        content = get_page_content(page_url)
        if not content:
            logger.error(f"Impossibile ottenere il contenuto della pagina: {page_url}")
            return None

        # Cerca tutti i possibili pattern per URL M3U8
        patterns = [
            # Pattern comune per URL M3U8
            r'(https?://[^"\'\s]+\.m3u8)',
            # Pattern per URL M3U8 in iframe src
            r'iframe.+?src=["\'](https?://[^"\']+)["\']',
            # Pattern per variabili JavaScript che contengono URL
            r'var\s+\w+\s*=\s*["\'](https?://[^"\']+\.m3u8)["\']',
            # Pattern per attributi data-
            r'data-\w+=["\'](https?://[^"\']+\.m3u8)["\']'
        ]

        # Cerca usando ciascun pattern
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                for match in matches:
                    if '.m3u8' in match:
                        logger.info(f"URL M3U8 trovato: {match}")
                        return match

        # Se non troviamo M3U8 direttamente, cerca iframe che potrebbero contenerlo
        soup = BeautifulSoup(content, 'html.parser')
        iframes = soup.find_all('iframe')

        for iframe in iframes:
            iframe_src = iframe.get('src')
            if iframe_src:
                # Aggiungi http:// se manca
                if not iframe_src.startswith('http'):
                    if iframe_src.startswith('//'):
                        iframe_src = 'https:' + iframe_src
                    else:
                        iframe_src = URL_BASE + iframe_src

                logger.info(f"Controllando iframe: {iframe_src}")
                iframe_content = get_page_content(iframe_src)

                if iframe_content:
                    # Cerca URL M3U8 nell'iframe
                    for pattern in patterns:
                        matches = re.findall(pattern, iframe_content)
                        if matches:
                            for match in matches:
                                if '.m3u8' in match:
                                    logger.info(f"URL M3U8 trovato nell'iframe: {match}")
                                    return match

        # Cerchiamo anche redirezioni JavaScript
        redirect_patterns = [
            r'window\.location\.href\s*=\s*["\'](https?://[^"\']+)["\']',
            r'location\.replace\(["\'](https?://[^"\']+)["\']\)'
        ]

        for pattern in redirect_patterns:
            matches = re.findall(pattern, content)
            if matches and matches[0]:
                redirect_url = matches[0]
                logger.info(f"Trovato reindirizzamento a: {redirect_url}")

                # Controlla se il reindirizzamento porta direttamente a un M3U8
                if '.m3u8' in redirect_url:
                    return redirect_url

                # Altrimenti, segui il reindirizzamento e cerca M3U8 lì
                redirect_content = get_page_content(redirect_url)
                if redirect_content:
                    for pattern in patterns:
                        matches = re.findall(pattern, redirect_content)
                        if matches:
                            for match in matches:
                                if '.m3u8' in match:
                                    logger.info(f"URL M3U8 trovato nella pagina di reindirizzamento: {match}")
                                    return match

        logger.warning(f"Nessun URL M3U8 trovato per: {page_url}")
        return None
    except Exception as e:
        logger.error(f"Errore nell'estrazione dell'URL M3U8: {e}")
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

            # Estrai URL M3U8
            # Aggiungi un piccolo delay per non sovraccaricare il server
            time.sleep(2)
            stream_url = extract_m3u8_url(match_url)

            if stream_url:
                partite_trovate.append((title, stream_url))

    # Crea il file M3U8
    if create_m3u8_file(partite_trovate):
        logger.info(f"Aggiornamento completato: {len(partite_trovate)} partite di Serie A aggiunte")
    else:
        logger.warning("Aggiornamento non riuscito")


if __name__ == "__main__":
    main()
