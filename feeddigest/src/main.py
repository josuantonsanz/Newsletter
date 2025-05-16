import logging
import json
from datetime import datetime
from pathlib import Path

from .. import config  # Uso de importación relativa
from .collector import collect_all_articles
from .classifier import classify_and_filter_articles
from .synthesizer import synthesize_data
from .generator import generate_daily_newsletter, generate_archive_index

logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def save_processed_articles_to_history(classified_articles, date_str):
    """
    Guarda los artículos clasificados y filtrados (antes de la síntesis) en el historial.
    Estos datos pueden ser usados por el generador de resúmenes semanales.
    """
    try:
        # Aplanar la estructura de classified_articles (dict de listas) a una sola lista para el historial
        all_processed_articles = []
        for category_articles in classified_articles.values():
            all_processed_articles.extend(category_articles)

        if not all_processed_articles:
            logger.info(f"No hay artículos procesados para guardar en el historial del {date_str}.")
            return

        history_file_path = config.HISTORY_DIR / f"{date_str}.json"
        with open(history_file_path, 'w', encoding='utf-8') as f:
            json.dump(all_processed_articles, f, indent=2, ensure_ascii=False)
        logger.info(f"Artículos procesados guardados en: {history_file_path}")
    except Exception as e:
        logger.error(f"Error guardando artículos procesados en el historial: {e}")


def run_daily_digest():
    """
    Ejecuta el proceso completo de FeedDigest para la generación diaria.
    """
    start_time = datetime.now()
    logger.info("Iniciando el proceso de FeedDigest diario...")

    today_str = start_time.strftime("%Y-%m-%d")

    # 1. Recolectar artículos
    logger.info("Fase 1: Recolección de artículos RSS...")
    raw_articles = collect_all_articles()
    if not raw_articles:
        logger.info("No se recolectaron artículos. Finalizando proceso.")
        return
    logger.info(f"Recolectados {len(raw_articles)} artículos en total.")

    # 2. Clasificar y Filtrar
    logger.info("Fase 2: Clasificación y filtrado de artículos...")
    classified_articles = classify_and_filter_articles(raw_articles)
    num_relevant_articles = sum(len(arts) for arts in classified_articles.values())
    if num_relevant_articles == 0:
        logger.info("No quedaron artículos relevantes después de la clasificación y filtrado. Finalizando.")
        # Aún así, generamos una página vacía para indicar que se ejecutó
        generate_daily_newsletter({}, today_str)
        generate_archive_index()  # Actualizar el archivo de todas formas
        return
    logger.info(f"Clasificados {num_relevant_articles} artículos relevantes en {len(classified_articles)} categorías.")

    # Guardar artículos clasificados y filtrados en el historial para el resumen semanal
    save_processed_articles_to_history(classified_articles, today_str)

    # 3. Analizar y Sintetizar
    logger.info("Fase 3: Análisis y síntesis de contenido...")
    synthesized_content = synthesize_data(classified_articles)
    if not any(synthesized_content.values()):  # Check si hay algún contenido sintetizado
        logger.info("No se generó contenido sintetizado. Finalizando.")
        generate_daily_newsletter({}, today_str)  # Generar página vacía
        generate_archive_index()
        return
    logger.info("Síntesis completada.")

    # 4. Generar Newsletter
    logger.info("Fase 4: Generación de la newsletter HTML...")
    generate_daily_newsletter(synthesized_content, today_str)

    # 5. Actualizar índice del archivo
    logger.info("Fase 5: Actualización del índice del archivo...")
    generate_archive_index()

    end_time = datetime.now()
    logger.info(f"Proceso de FeedDigest diario completado en {end_time - start_time}.")
    logger.info(f"Resultados publicados en: {config.OUTPUT_DIR}")


if __name__ == "__main__":
    # Esto permite ejecutar el script directamente con `python -m feeddigest.src.main`
    # desde el directorio raíz del proyecto `feeddigest/`.
    run_daily_digest()