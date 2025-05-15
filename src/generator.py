from jinja2 import Environment, FileSystemLoader, select_autoescape
import logging
from markupsafe import Markup
from datetime import datetime
import os
import json
import re # Para el filtro de reemplazo
from .. import config

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)


def get_jinja_env():
    env = Environment(
        loader=FileSystemLoader(config.TEMPLATES_DIR),
        autoescape=select_autoescape(['html', 'xml'])  # Buena práctica para seguridad
    )

    def replace_refs_with_links(text_with_placeholders, articles_details):
        if not text_with_placeholders or not articles_details:
            return text_with_placeholders

        # Crear un diccionario para buscar fácilmente los detalles del artículo por ID (1-based)
        articles_map = {int(details['id']): details for details in articles_details}

        def replacer(match):
            try:
                ref_id = int(match.group(1))  # El número sigue siendo importante para encontrar el enlace correcto
                if ref_id in articles_map:
                    article_detail = articles_map[ref_id]
                    # Ahora solo generamos el icono como enlace, el número [N] original se reemplaza.
                    # El title del enlace ahora es más importante para saber a qué se refiere.
                    # El title del enlace podría ser "Fuente [N]: {título del artículo}"
                    link_title = f"Fuente [{ref_id}]: {article_detail['title']}"
                    return Markup(
                        f'<a href="{article_detail["url"]}" target="_blank" title="{link_title}" class="inline-ref-arrow-only"><span class="ref-icon">↗</span></a>')
                else:
                    # Si no se encuentra el ID, devolvemos el placeholder original [N] para que no se pierda la info
                    # o podrías optar por no mostrar nada, pero podría ser confuso si el LLM generó un [N] inválido.
                    return match.group(0)
            except (ValueError, KeyError) as e:
                logger.warning(f"Error al procesar referencia '{match.group(0)}': {e}")
                return match.group(0)

        # Usar re.sub con una función de reemplazo
        # El patrón busca [ seguido de uno o más dígitos seguido de ]
        processed_text = re.sub(r'\[(\d+)\]', replacer, text_with_placeholders)
        return Markup(processed_text)  # Asegurar que el resultado final sea tratado como HTML

    env.filters['replace_refs'] = replace_refs_with_links  # Registrar el filtro
    return env


def generate_daily_newsletter(synthesized_content, date_str):
    env = get_jinja_env()  # Obtener el entorno con el filtro registrado
    template = env.get_template("daily.html")

    # ... (tu lógica para ordered_content y nav_links) ...
    prefs = {}  # Cargar preferencias si es necesario para el orden
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    except Exception:
        logger.warning("No se pudo cargar preferences.json para el generador (orden).")

    categories_order = prefs.get("global", {}).get("categories_order", list(synthesized_content.keys()))

    ordered_content_for_template = {}
    for cat_name in categories_order:
        if cat_name in synthesized_content and synthesized_content[cat_name]:
            # Cada item en synthesized_content[cat_name] ahora tiene 'text_with_placeholders' y 'original_articles_details'
            ordered_content_for_template[cat_name] = synthesized_content[cat_name]

    nav_links = {
        "today_file": f"{date_str}.html",
        "yesterday_file": "yesterday.html",
        "this_week_file": "current_weekly_summary.html",
        "archive_index_file": "archive/index.html"
    }
    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    html_output = template.render(
        title=f"FeedDigest - {date_str}",
        date_published=date_str,
        # Asegúrate de que 'categories' ahora espera la nueva estructura de synthesized_content
        categories=ordered_content_for_template,
        nav_links=nav_links,
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str
    )
    # ... (resto de la función para guardar el archivo) ...
    daily_filename = f"{date_str}.html"
    output_path = config.ARCHIVE_DIR / daily_filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"Newsletter diaria generada: {output_path}")

    index_path = config.OUTPUT_DIR / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"index.html actualizado para apuntar a: {daily_filename}")

    return output_path


def generate_archive_index():
    env = get_jinja_env()
    template = env.get_template("archive_index.html")

    archived_editions = []
    for filename in sorted(os.listdir(config.ARCHIVE_DIR), reverse=True):
        if filename.endswith(".html") and filename not in ["index.html",
                                                           "current_weekly_summary.html"]:  # Excluir índices
            date_str = filename.replace(".html", "")
            archived_editions.append({"date": date_str, "url": filename})

    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")  # <--- AÑADIDO

    html_output = template.render(
        title="Archivo de Ediciones - FeedDigest",
        editions=archived_editions,
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str  # <--- AÑADIDO AL CONTEXTO
    )

    output_path = config.ARCHIVE_DIR / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"Índice del archivo generado: {output_path}")
    return output_path


def generate_weekly_summary_page(summary_content, week_str):
    env = get_jinja_env()
    template = env.get_template("weekly_summary.html")

    prefs = {}
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    except Exception:
        logger.warning("No se pudo cargar preferences.json para el generador semanal.")

    categories_order = prefs.get("global", {}).get("categories_order", list(summary_content.keys()))

    ordered_content = {
        cat: summary_content.get(cat, []) for cat in categories_order if summary_content.get(cat)
    }

    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")  # <--- AÑADIDO

    html_output = template.render(
        title=f"Resumen Semanal - {week_str} - FeedDigest",
        week_identifier=week_str,
        categories=ordered_content,
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str  # <--- AÑADIDO AL CONTEXTO
    )

    filename = f"weekly-{week_str}.html"
    output_path = config.ARCHIVE_DIR / filename
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"Resumen semanal generado: {output_path}")

    # Actualizar también un enlace genérico al resumen semanal más reciente
    current_weekly_path = config.OUTPUT_DIR / "current_weekly_summary.html"
    # Eliminar el archivo si existe (para evitar problemas con symlinks en algunos sistemas o si cambias a copia)
    if os.path.exists(current_weekly_path):
        os.remove(current_weekly_path)
    try:
        # Crear un symlink relativo desde output/ a archive/weekly-...html
        # Esto es más eficiente que copiar.
        # Necesitamos la ruta relativa desde current_weekly_path hasta output_path
        # output_path es config.ARCHIVE_DIR / filename
        # current_weekly_path es config.OUTPUT_DIR / "current_weekly_summary.html"
        # Asumiendo que ARCHIVE_DIR es output/archive/
        relative_symlink_target = Path("archive") / filename
        os.symlink(relative_symlink_target, current_weekly_path)
        logger.info(f"Symlink 'current_weekly_summary.html' creado apuntando a {relative_symlink_target}")
    except Exception as e:  # shutil.copy2(output_path, current_weekly_path)
        logger.error(f"No se pudo crear el symlink para current_weekly_summary.html. Error: {e}. Intenta copiar.")
        try:
            import shutil
            shutil.copy2(output_path, current_weekly_path)
            logger.info(f"Copiado '{filename}' a 'current_weekly_summary.html'")
        except Exception as copy_e:
            logger.error(f"Error al copiar el resumen semanal: {copy_e}")

    return output_path