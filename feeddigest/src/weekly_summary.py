import json
import logging
from datetime import datetime, timedelta
import os
from .. import config
from .synthesizer import synthesize_data  # Reutilizar el sintetizador
from .generator import generate_weekly_summary_page  # Reutilizar el generador

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)


def load_articles_from_history(days=7):
    """
    Carga artículos de los archivos de historial de los últimos 'days' días.
    Asume que los archivos de historial se guardan como YYYY-MM-DD.json
    y contienen una lista de objetos de artículo (antes de la síntesis).
    """
    articles_from_week = []
    base_path = config.HISTORY_DIR

    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        history_file_path = base_path / f"{date.strftime('%Y-%m-%d')}.json"
        if os.path.exists(history_file_path):
            try:
                with open(history_file_path, 'r', encoding='utf-8') as f:
                    daily_articles = json.load(f)  # Asume que es una lista de artículos
                    articles_from_week.extend(daily_articles)
                logger.info(f"Cargados {len(daily_articles)} artículos de {history_file_path}")
            except Exception as e:
                logger.error(f"Error cargando historial de {history_file_path}: {e}")
        else:
            logger.warning(f"Archivo de historial no encontrado: {history_file_path}")

    # Eliminar duplicados (basado en 'id' o 'link') si es necesario, aunque no debería haber
    # si cada archivo diario es único.
    # unique_articles = {article['id']: article for article in articles_from_week}.values()
    # logger.info(f"Total de artículos únicos de la semana: {len(unique_articles)}")
    # return list(unique_articles)

    logger.info(
        f"Total de artículos (potencialmente duplicados si no se guarda estado procesado) de la semana: {len(articles_from_week)}")
    return articles_from_week


def select_weekly_highlights(all_weekly_articles, classified_articles_by_day):
    """
    Selecciona los "highlights" de la semana.
    Esta es una lógica placeholder. Podría ser más sofisticada:
    - Artículos con más interacciones (si hubiera feedback).
    - Artículos de temas recurrentes.
    - Usar IA para identificar los más impactantes.

    Por ahora, simplemente toma una muestra o los más recientes de cada categoría
    de los `classified_articles_by_day`.

    `classified_articles_by_day` debería ser una estructura como:
    {
        "YYYY-MM-DD": {
            "Tecnología": [article1, article2], ...
        }, ...
    }
    Esta función necesita que `main.py` guarde los artículos *clasificados* y *filtrados*
    diariamente, no solo los recolectados.
    Alternativamente, si `load_articles_from_history` carga artículos *brutos*,
    se necesitaría volver a clasificarlos aquí.

    Simplificación: Vamos a asumir que `main.py` guarda los artículos *clasificados y filtrados*
    en un formato que `load_articles_from_history` puede leer, y luego
    este método los agrupa por categoría para toda la semana.
    """

    # Este es un placeholder muy simplificado.
    # Se necesita un mecanismo para obtener los artículos *ya clasificados y filtrados*
    # de la semana. El `main.py` debería guardar estos.
    # Por ahora, vamos a simular que tenemos estos artículos.

    weekly_highlights_by_category = {}

    # Supongamos que all_weekly_articles es una lista de artículos ya filtrados y con 'assigned_category'
    # Agruparlos por categoría
    temp_classified = {}
    for article in all_weekly_articles:
        category = article.get('assigned_category', 'General')
        temp_classified.setdefault(category, []).append(article)

    # Luego, de cada categoría, seleccionar algunos (ej. los N más recientes o aleatorios)
    # Esta lógica es muy básica y necesita refinamiento.
    prefs = {}
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    except Exception:
        logger.warning("No se pudo cargar preferences.json para el resumen semanal.")

    max_highlights_per_category = prefs.get("global", {}).get("max_articles_per_category_weekly", 3)  # Nueva config

    for category, articles in temp_classified.items():
        # Ordenar por fecha (asumiendo que 'published_date' está presente y es comparable)
        # y tomar los más recientes
        sorted_articles = sorted(articles, key=lambda x: x.get('published_date', ''), reverse=True)
        weekly_highlights_by_category[category] = sorted_articles[:max_highlights_per_category]

    logger.info(
        f"Highlights seleccionados para el resumen semanal: {sum(len(v) for v in weekly_highlights_by_category.values())} artículos.")
    return weekly_highlights_by_category


def generate_weekly_summary():
    """
    Función principal para generar el resumen semanal.
    """
    logger.info("Iniciando generación de resumen semanal...")

    # 1. Cargar artículos de la semana.
    #    Esto asume que main.py guarda los artículos *filtrados y categorizados* diariamente.
    #    El formato guardado en history/YYYY-MM-DD.json debería ser la salida de classifier.py

    #  Modificamos load_articles_from_history para que cargue una estructura de datos
    #  que contenga artículos ya categorizados. O, si carga artículos brutos,
    #  necesitaríamos ejecutar una parte de classifier.py aquí.

    #  Simplificación: Suponemos que `load_articles_from_history` devuelve una lista plana
    #  de artículos que ya tienen 'assigned_category'.

    weekly_processed_articles = load_articles_from_history(days=7)  # Carga artículos con 'assigned_category'

    if not weekly_processed_articles:
        logger.info("No hay artículos en el historial de la semana para generar resumen.")
        return

    # 2. Seleccionar "highlights" (esta función es un placeholder)
    #    En una implementación real, esta parte sería más compleja.
    #    Por ahora, simplemente agrupamos los artículos ya categorizados.
    highlights_by_category = {}
    for article in weekly_processed_articles:
        category = article.get('assigned_category', 'General')  # Asegurarse que el artículo tenga esto
        # Aplicar algún criterio para "highlight", ej. solo los N más recientes o importantes.
        # Para esta demo, los tomaremos todos y dejaremos que el sintetizador y el generador limiten.
        highlights_by_category.setdefault(category, []).append(article)

    # Aplicar un límite similar al diario si es necesario, o uno específico para el semanal
    prefs = {}
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    except Exception:
        pass  # Usar defaults

    max_articles_cat_weekly = prefs.get("global", {}).get("max_articles_per_category_weekly",
                                                          config.MAX_ARTICLES_PER_CATEGORY_DEFAULT * 2)  # Ejemplo: el doble que el diario

    final_highlights = {}
    for cat, arts in highlights_by_category.items():
        # Podríamos ordenar por fecha y tomar los más recientes, o aplicar otra lógica de "highlight"
        arts.sort(key=lambda x: x.get('published_date', ''), reverse=True)
        final_highlights[cat] = arts[:max_articles_cat_weekly]

    if not any(final_highlights.values()):
        logger.info("No se seleccionaron highlights para el resumen semanal.")
        return

    # 3. Sintetizar los highlights
    #    Reutilizamos la lógica de synthesizer.py
    logger.info("Sintetizando highlights semanales...")
    synthesized_weekly_content = synthesize_data(
        final_highlights)  # synthesize_data espera un dict {categoria: [artículos]}

    # 4. Generar la página HTML del resumen semanal
    #    Reutilizamos la lógica de generator.py
    week_str = datetime.now().strftime("%Y-W%U")  # Ejemplo: 2025-W20
    logger.info(f"Generando página HTML para el resumen semanal: {week_str}")
    generate_weekly_summary_page(synthesized_weekly_content, week_str)

    logger.info("Resumen semanal generado exitosamente.")


if __name__ == '__main__':
    # Para pruebas:
    # 1. Asegúrate de que existan algunos archivos en data/history/YYYY-MM-DD.json
    #    con artículos que incluyan 'assigned_category' y 'published_date'.
    # Ejemplo de un archivo data/history/2025-05-14.json:
    # [
    #   {"id": "link1", "title": "Articulo 1 Tech", "content_text": "...", "published_date": "2025-05-14T10:00:00", "assigned_category": "Tecnología", "link": "link1"},
    #   {"id": "link2", "title": "Articulo 2 Deportes", "content_text": "...", "published_date": "2025-05-14T11:00:00", "assigned_category": "Deportes", "link": "link2"}
    # ]
    # Puedes crear archivos dummy manualmente para probar.

    # Crear archivos dummy para probar
    # (Esto normalmente lo haría main.py)
    # today_hist_dir = config.HISTORY_DIR
    # today_hist_dir.mkdir(parents=True, exist_ok=True)
    # dummy_date = datetime.now() - timedelta(days=1)
    # dummy_file = today_hist_dir / f"{dummy_date.strftime('%Y-%m-%d')}.json"
    # dummy_data = [
    #    {"id": "test1", "title": "Weekly Test Article 1", "content_text": "Content for weekly test 1", "published_date": (dummy_date).isoformat(), "assigned_category": "Tecnología", "link": "test1.com"},
    #    {"id": "test2", "title": "Weekly Test Article 2", "content_text": "Content for weekly test 2", "published_date": (dummy_date - timedelta(hours=1)).isoformat(), "assigned_category": "Noticias", "link": "test2.com"}
    # ]
    # with open(dummy_file, 'w', encoding='utf-8') as f:
    #    json.dump(dummy_data, f)
    # print(f"Dummy history file created: {dummy_file}")

    generate_weekly_summary()