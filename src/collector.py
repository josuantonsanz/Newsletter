import feedparser
import json
import logging
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup  # <--- AÑADIDO para parsear HTML
from .. import config

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)


def load_sources():
    """Carga las fuentes RSS desde el archivo de configuración."""
    try:
        with open(config.SOURCES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("sources", [])
    except FileNotFoundError:
        logger.error(f"Archivo de fuentes no encontrado: {config.SOURCES_FILE}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error decodificando el archivo JSON de fuentes: {config.SOURCES_FILE}")
        return []


def fetch_articles_from_source(source_config):
    """Recupera artículos de una única fuente RSS, filtrando por los publicados en las últimas 24 horas."""
    articles = []
    source_display_name = source_config.get('name', source_config['url'])
    logger.info(f"Procesando fuente: {source_display_name}")

    try:
        feed = feedparser.parse(source_config['url'])
    except Exception as e:
        logger.error(f"No se pudo parsear el feed de {source_display_name}: {e}")
        return []

    time_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles_processed_count = 0
    articles_added_count = 0

    for entry in feed.entries:
        articles_processed_count += 1
        published_dt = None
        published_date_iso = None
        title = entry.get('title', 'Sin título')  # Obtener título antes para logs

        # --- TU LÓGICA DE GESTIÓN DE FECHAS (MANTENIDA) ---
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                dt_naive = datetime(*entry.published_parsed[:6])
                if dt_naive.tzinfo is None:
                    published_dt = dt_naive.replace(tzinfo=timezone.utc)
                else:
                    published_dt = dt_naive.astimezone(timezone.utc)
                published_date_iso = published_dt.isoformat()
            except Exception as e:
                logger.warning(
                    f"No se pudo parsear la fecha 'published_parsed' para '{title}': {entry.get('published', 'Fecha no disponible')}. Error: {e}. Se usará la fecha actual.")
                published_dt = datetime.now(timezone.utc)
                published_date_iso = published_dt.isoformat()
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                dt_naive = datetime(*entry.updated_parsed[:6])
                if dt_naive.tzinfo is None:
                    published_dt = dt_naive.replace(tzinfo=timezone.utc)
                else:
                    published_dt = dt_naive.astimezone(timezone.utc)
                published_date_iso = published_dt.isoformat()
                logger.debug(f"Usando 'updated_parsed' para artículo '{title}'.")
            except Exception as e:
                logger.warning(
                    f"No se pudo parsear 'updated_parsed' para '{title}'. Se usará fecha actual. Error: {e}")
                published_dt = datetime.now(timezone.utc)
                published_date_iso = published_dt.isoformat()
        else:
            logger.warning(
                f"Artículo '{title}' no tiene fecha de publicación/actualización. Asumiendo fecha actual.")
            published_dt = datetime.now(timezone.utc)
            published_date_iso = published_dt.isoformat()

        # --- TU FILTRADO POR FECHA (MANTENIDO) ---
        if published_dt < time_cutoff:
            logger.debug(f"Artículo DESCARTADO (muy antiguo: {published_date_iso}): {title}")
            continue

        # --- EXTRACCIÓN Y LIMPIEZA DE CONTENIDO (FUSIONADO Y MEJORADO) ---
        link = entry.get('link', '')

        # Validar que tengamos un enlace, sino el artículo es poco útil
        if not link:
            logger.warning(f"Artículo '{title}' de '{source_display_name}' no tiene URL (link). Descartado.")
            continue

        content_html = ""
        # Priorizar 'content' si existe y es una lista (común en feeds más ricos)
        if 'content' in entry and isinstance(entry.content, list) and entry.content:
            for content_item in entry.content:
                if isinstance(content_item, feedparser.FeedParserDict) and \
                        content_item.get('value') and \
                        content_item.get('type', '').startswith('text/'):
                    content_html = content_item.value
                    break  # Usar el primer contenido de texto válido

        # Fallback a summary si no se encontró en 'content'
        if not content_html and 'summary' in entry:
            content_html = entry.summary
        # Fallback a description si tampoco en 'summary'
        elif not content_html and 'description' in entry:
            content_html = entry.description

        # Usar BeautifulSoup para obtener texto plano del content_html resultante
        if content_html:  # Solo si tenemos algo de HTML para parsear
            soup = BeautifulSoup(content_html, 'html.parser')
            text_content = soup.get_text(separator=' ', strip=True)
        else:
            text_content = ""  # Si no hay HTML, no hay texto
            logger.debug(
                f"Artículo '{title}' de '{source_display_name}' no tiene 'content', 'summary', ni 'description' HTML.")

        # Validar que tengamos algún contenido de texto, sino el artículo es poco útil para IA
        if not text_content.strip():  # strip() para verificar si solo son espacios en blanco
            logger.warning(
                f"Artículo '{title}' de '{source_display_name}' no tiene contenido de texto legible después de la limpieza. Descartado.")
            continue

        # --- CONSTRUCCIÓN DEL ARTÍCULO (MANTENIENDO TU ID) ---
        articles_added_count += 1  # Mover aquí, solo se incrementa si el artículo realmente se añade

        articles.append({
            "id": link,  # Usar link como ID primario es generalmente más robusto
            "title": title,
            "link": link,
            "published_date": published_date_iso,
            "content_raw": content_html,  # Guardar el HTML original por si acaso
            "content_text": text_content,  # El texto limpio
            "source_name": source_config.get('name'),
            "default_category": source_config.get('default_category', 'General'),
            "source_keywords": source_config.get('keywords', []),
            "source_blacklist": source_config.get('blacklist', [])
        })

    logger.info(
        f"Fuente '{source_display_name}': {articles_processed_count} artículos encontrados en el feed, {articles_added_count} añadidos (post-filtro de fecha y contenido).")
    return articles


def collect_all_articles():
    """Recolecta artículos de todas las fuentes configuradas."""
    sources = load_sources()
    all_articles = []
    # total_articles_from_feeds = 0 # No se usa esta variable, se puede quitar

    for source_config in sources:
        try:
            articles_from_source = fetch_articles_from_source(source_config)
            all_articles.extend(articles_from_source)
        except Exception as e:
            logger.error(f"Error grave procesando la fuente {source_config.get('name', source_config['url'])}: {e}")

    logger.info(f"Total de artículos recolectados (post-filtros) de todas las fuentes: {len(all_articles)}")
    return all_articles


if __name__ == '__main__':
    # Para pruebas directas del módulo
    collected_articles = collect_all_articles()
    if collected_articles:
        print(f"\nTotal de artículos recolectados para prueba: {len(collected_articles)}")
        print(f"Ejemplo de artículo recolectado (de las últimas 24 horas y con contenido):")
        article_example = collected_articles[0]
        print(f"  ID: {article_example['id']}")
        print(f"  Título: {article_example['title']}")
        print(f"  Link: {article_example['link']}")
        print(f"  Fuente: {article_example['source_name']}")
        print(f"  Fecha Publicación: {article_example['published_date']}")
        print(f"  Texto (primeros 150 chars): {article_example['content_text'][:150]}...")
    else:
        print("No se recolectaron artículos que cumplan los criterios (últimas 24 horas, con link y contenido).")