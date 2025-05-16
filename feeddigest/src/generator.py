from jinja2 import Environment, FileSystemLoader, select_autoescape
import logging
# from markupsafe import Markup # No longer needed here for the filter
import markdown  # <-- IMPORT MARKDOWN LIBRARY
from datetime import datetime
import os
import json
import re
from pathlib import Path  # <-- IMPORT PATH
from .. import config

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)


# This Python function replaces the logic of the old Jinja filter.
# It converts placeholders like [1] into HTML links.
# This HTML will be embedded in the Markdown before final processing.
def convert_placeholders_to_html_links(text_with_placeholders, articles_details):
    if not text_with_placeholders or not articles_details:
        return text_with_placeholders

    articles_map = {int(details['id']): details for details in articles_details}

    def replacer(match):
        try:
            ref_id = int(match.group(1))
            if ref_id in articles_map:
                article_detail = articles_map[ref_id]
                link_title = f"Fuente {ref_id}: {article_detail['title']}"
                # Return the HTML string for the link directly
                return f'<a href="{article_detail["url"]}" target="_blank" title="{link_title}" class="inline-ref-arrow-only"><span class="ref-icon">↗</span></a>'
            else:
                return match.group(0)  # Keep placeholder if ID not found
        except (ValueError, KeyError) as e:
            logger.warning(f"Error al procesar referencia '{match.group(0)}': {e}")
            return match.group(0)

    processed_text = re.sub(r'\[(\d+)\]', replacer, text_with_placeholders)
    return processed_text


def get_jinja_env():
    env = Environment(
        loader=FileSystemLoader(config.TEMPLATES_DIR),
        autoescape=select_autoescape(['html', 'xml'])
    )
    # env.filters['replace_refs'] = replace_refs_with_links # Filter is no longer needed
    return env


def generate_daily_newsletter(synthesized_content, date_str):
    env = get_jinja_env()
    template = env.get_template("daily.html")

    prefs = {}
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
            prefs = json.load(f)
    except Exception:
        logger.warning("No se pudo cargar preferences.json para el generador (orden).")

    categories_order = prefs.get("global", {}).get("categories_order", list(synthesized_content.keys()))

    ordered_content_for_template = {}
    for cat_name in categories_order:
        if cat_name in synthesized_content and synthesized_content[cat_name]:
            processed_items_for_category = []
            for item_data in synthesized_content[cat_name]:
                # 1. Get the raw text (assumed to be Markdown + [1] placeholders)
                markdown_text_with_placeholders = item_data.get('text_with_placeholders', '')
                original_articles = item_data.get('original_articles_details', [])

                # 2. Convert [1] placeholders to embedded HTML links
                text_with_embedded_html_links = convert_placeholders_to_html_links(
                    markdown_text_with_placeholders,
                    original_articles
                )

                # 3. Convert the full Markdown (with embedded HTML links) to final HTML
                # 'extra' includes tables, fenced_code, footnotes, etc.
                # 'sane_lists' helps with list parsing.
                final_html_content = markdown.markdown(text_with_embedded_html_links,
                                                       extensions=['extra', 'sane_lists', 'nl2br'])

                # Create a new item dictionary or update item_data
                # It's safer to create a new one to avoid modifying the original dict if it's used elsewhere
                processed_item = item_data.copy()  # Start with a copy
                processed_item['content_html'] = final_html_content
                # Remove old keys if they are no longer directly used by the template for this content
                # processed_item.pop('text_with_placeholders', None)
                # processed_item.pop('original_articles_details', None) # Or keep if needed for other things
                processed_items_for_category.append(processed_item)

            ordered_content_for_template[cat_name] = processed_items_for_category

    nav_links = {
        "today_file": f"{date_str}.html",  # This should ideally be just the filename, path handled by root
        "yesterday_file": "yesterday.html",  # Placeholder, logic needed
        "this_week_file": "current_weekly_summary.html",  # Relative to output dir
        "archive_index_file": "archive/index.html"  # Relative to output dir
    }
    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    html_output = template.render(
        title=f"FeedDigest - {date_str}",
        date_published=date_str,
        categories=ordered_content_for_template,  # Pass the content with 'content_html'
        nav_links=nav_links,
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str
    )

    daily_filename = f"{date_str}.html"
    output_path = config.ARCHIVE_DIR / daily_filename  # Store in archive
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"Newsletter diaria generada: {output_path}")

    # Update index.html in the root output directory to be the latest daily
    index_path = config.OUTPUT_DIR / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"index.html actualizado para apuntar a la edición de: {date_str}")

    return output_path


def generate_archive_index():
    env = get_jinja_env()
    template = env.get_template("archive_index.html")

    archived_editions = []
    # Ensure ARCHIVE_DIR is a Path object if not already
    archive_path_obj = Path(config.ARCHIVE_DIR)
    for filename in sorted(archive_path_obj.iterdir(), reverse=True):
        if filename.is_file() and filename.name.endswith(".html") and \
                filename.name not in ["index.html", "current_weekly_summary.html"]:
            date_str = filename.stem  # .stem gets filename without extension
            # URL should be relative to archive/index.html for items in the same directory
            archived_editions.append({"date": date_str, "url": filename.name})

    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    html_output = template.render(
        title="Archivo de Ediciones - FeedDigest",
        editions=archived_editions,
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str
    )

    output_path = archive_path_obj / "index.html"
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

    ordered_content_for_template = {}
    for cat_name in categories_order:
        if cat_name in summary_content and summary_content.get(cat_name):
            processed_items_for_category = []
            for item_data in summary_content[cat_name]:
                # Assuming item_data['text'] contains the Markdown for weekly summaries
                markdown_input = item_data.get('text', '')

                # Convert Markdown to HTML
                # 'extra' includes tables, fenced_code, footnotes, etc.
                # 'sane_lists' helps with list parsing.
                # 'nl2br' converts newlines to <br>, useful if source text uses single newlines for breaks
                final_html_content = markdown.markdown(markdown_input, extensions=['extra', 'sane_lists', 'nl2br'])

                processed_item = item_data.copy()
                processed_item['content_html'] = final_html_content
                # processed_item.pop('text', None) # Optionally remove old key
                # If weekly items also have 'references', decide if they are still needed separately
                # or if they should be embedded in the Markdown. For now, assuming they might still be separate.
                processed_items_for_category.append(processed_item)

            ordered_content_for_template[cat_name] = processed_items_for_category

    current_datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    html_output = template.render(
        title=f"Resumen Semanal - {week_str} - FeedDigest",
        week_identifier=week_str,
        categories=ordered_content_for_template,  # Pass content with 'content_html'
        current_year=datetime.now().year,
        generated_at_datetime=current_datetime_str
    )

    filename = f"weekly-{week_str}.html"
    output_path = Path(config.ARCHIVE_DIR) / filename  # Ensure Path object
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)
    logger.info(f"Resumen semanal generado: {output_path}")

    current_weekly_path = Path(config.OUTPUT_DIR) / "current_weekly_summary.html"
    if current_weekly_path.exists() or current_weekly_path.is_symlink():
        current_weekly_path.unlink()

    try:
        # Target for symlink needs to be relative to the symlink's location
        # current_weekly_path is in config.OUTPUT_DIR
        # output_path is in config.ARCHIVE_DIR (which is usually config.OUTPUT_DIR / "archive")
        relative_symlink_target = Path(os.path.relpath(output_path, config.OUTPUT_DIR))
        os.symlink(relative_symlink_target, current_weekly_path)
        logger.info(f"Symlink 'current_weekly_summary.html' creado apuntando a {relative_symlink_target}")
    except Exception as e:
        logger.error(f"No se pudo crear el symlink para current_weekly_summary.html. Error: {e}. Intentando copiar.")
        try:
            import shutil
            shutil.copy2(output_path, current_weekly_path)
            logger.info(f"Copiado '{filename}' a 'current_weekly_summary.html'")
        except Exception as copy_e:
            logger.error(f"Error al copiar el resumen semanal: {copy_e}")

    return output_path