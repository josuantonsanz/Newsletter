import json
import logging
import re  # Para parsear referencias
import llm  # <--- AÑADIDO
from .. import config

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# --- Carga de Configuraciones --- (similar a classifier.py)
_prompts_cache = None


def get_prompts():
    global _prompts_cache
    if _prompts_cache is None:
        try:
            with open(config.PROMPTS_FILE, 'r', encoding='utf-8') as f:
                _prompts_cache = json.load(f)
        except FileNotFoundError:
            logger.error(f"Archivo de prompts no encontrado: {config.PROMPTS_FILE}")
            _prompts_cache = {}
        except json.JSONDecodeError:
            logger.error(f"Error decodificando el archivo JSON de prompts: {config.PROMPTS_FILE}")
            _prompts_cache = {}
    return _prompts_cache


# --- Modelo de IA ---
try:
    model_synthesis = llm.get_model(config.LLM_MODEL_SYNTHESIS)
    # model_synthesis.options.timeout = 60 # Ejemplo de timeout más largo para síntesis
except Exception as e:
    logger.error(f"Error al cargar modelo LLM para síntesis: {e}. La síntesis no operará correctamente.")
    model_synthesis = None


def parse_synthesis_response(response_text, original_articles):
    """
    Intenta parsear el texto sintetizado y las referencias.
    El prompt pide referencias como [1], [2].
    Esta función es un intento básico. Podría necesitar ser más robusta.
    """
    # El texto sintetizado es la respuesta directa
    synthesized_text = response_text.strip()

    # Extraer referencias (ej. [1], [2]) del texto sintetizado
    # y mapearlas a los artículos originales
    found_reference_indices = set()
    # Usar regex para encontrar todas las instancias de [N]
    for match in re.finditer(r'\[(\d+)\]', synthesized_text):
        try:
            ref_num = int(match.group(1))
            # El prompt usa index 1-based para referencias
            if 1 <= ref_num <= len(original_articles):
                found_reference_indices.add(ref_num - 1)  # Convertir a 0-based index
        except ValueError:
            logger.warning(f"Referencia no numérica encontrada en síntesis: {match.group(0)}")

    # Crear la lista de referencias basada en los índices encontrados
    references_for_item = []
    for i, article in enumerate(original_articles):
        if i in found_reference_indices:  # Si el artículo fue referenciado
            references_for_item.append({
                "id": i + 1,  # Mantener ID 1-based para el template
                "url": article['link'],
                "title": article['title']
            })

    # Si no se encuentran referencias explícitas en el texto pero hay artículos,
    # se podría decidir listar todos los artículos como referencias generales del párrafo.
    # Por ahora, solo listamos los explícitamente referenciados por el LLM.
    if not references_for_item and original_articles:
        logger.warning(
            f"LLM no incluyó referencias numéricas explícitas en la síntesis para la categoría. El texto fue: '{synthesized_text[:100]}...'")
        # Fallback: listar todos los artículos como referencias si no hay explícitas.
        # Opcional, dependiendo de si se quiere siempre la lista completa.
        # for i, article in enumerate(original_articles):
        #    references_for_item.append({
        #        "id": i + 1, "url": article['link'], "title": article['title']
        #    })

    return synthesized_text, references_for_item


def synthesize_category_articles(articles_in_category, category_name):
    if not model_synthesis:
        logger.warning(f"Modelo de síntesis no disponible para '{category_name}'. Se listarán títulos como fallback.")
        # Fallback simple
        items = []
        for i, article in enumerate(articles_in_category):
            items.append({
                "text_with_placeholders": f"{article['title']}. (Contenido no sintetizado por IA)",
                "original_articles_details": [{"id": j + 1, "url": art['link'], "title": art['title']} for j, art in
                                              enumerate(articles_in_category)]
            })
        return items

    if not articles_in_category:
        return []

    prompts = get_prompts()
    prompt_template = prompts.get("synthesis", {}).get("default")
    article_template = prompts.get("synthesis", {}).get("article_template")

    if not prompt_template or not article_template:
        logger.error(f"No se encontraron plantillas de prompt para síntesis en '{category_name}'. Listando títulos.")
        # Fallback (igual que arriba)
        items = []
        for i, article in enumerate(articles_in_category):
            items.append({
                "text_with_placeholders": f"{article['title']}. (Contenido no sintetizado por falta de prompt)",
                "original_articles_details": [{"id": j + 1, "url": art['link'], "title": art['title']} for j, art in
                                              enumerate(articles_in_category)]
            })
        return items

    articles_section_parts = []
    original_articles_details_for_template = []  # Para pasar al template
    for i, article in enumerate(articles_in_category):
        content_for_synthesis = article['content_text'][:1000]
        articles_section_parts.append(
            article_template.format(index=i + 1, title=article['title'], content=content_for_synthesis,
                                    url=article['link'])
        )
        original_articles_details_for_template.append({
            "id": i + 1,  # ID 1-based para el template
            "url": article['link'],
            "title": article['title']
        })

    articles_section_str = "\n\n".join(articles_section_parts)

    prompt = prompt_template.format(
        category=category_name,
        articles_section=articles_section_str
    )

    logger.info(
        f"Sintetizando (IA) para categoría '{category_name}' con {len(articles_in_category)} artículos (esperando refs inline)...")

    try:
        response = model_synthesis.prompt(prompt)
        synthesized_text_with_placeholders = response.text().strip()

        if not synthesized_text_with_placeholders:
            logger.warning(f"IA devolvió síntesis vacía para '{category_name}'.")
            # Fallback si la síntesis es vacía
            return [{
                "text_with_placeholders": "(Síntesis de IA vacía)",
                "original_articles_details": original_articles_details_for_template
            }]

        # El texto ya tiene [1], [2], etc. El template se encargará de reemplazarlos.
        return [{
            "text_with_placeholders": synthesized_text_with_placeholders,
            "original_articles_details": original_articles_details_for_template  # Pasar todos los detalles
        }]

    except Exception as e:
        logger.error(f"Error en llamada a LLM para síntesis de '{category_name}': {e}. Listando títulos.")
        # Fallback en caso de error
        items = []
        for i, article in enumerate(articles_in_category):  # Usar un bucle diferente para el fallback
            items.append({
                "text_with_placeholders": f"{article['title']}. (Error durante la síntesis por IA: {str(e)[:100]})",
                # Limitar longitud del error
                "original_articles_details": original_articles_details_for_template
            })
        return items

def synthesize_data(classified_articles):
    synthesized_content = {}
    prefs = {}
    try:
        with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f: # Corrección aquí
            prefs = json.load(f)
    except Exception:
        logger.warning("No se pudo cargar preferences.json para el sintetizador (orden de categorías).")

    categories_order = prefs.get("global", {}).get("categories_order", list(classified_articles.keys()))

    for cat_name in classified_articles.keys():
        if cat_name not in categories_order:
            categories_order.append(cat_name)

    for category_name in categories_order:
        if category_name not in classified_articles or not classified_articles[category_name]:
            continue

        articles_in_category = classified_articles[category_name]

        logger.info(f"Preparando para sintetizar {len(articles_in_category)} artículos para la categoría: {category_name}")
        synthesized_items = synthesize_category_articles(articles_in_category, category_name)
        synthesized_content[category_name] = synthesized_items

    return synthesized_content


if __name__ == '__main__':
    sample_classified_articles = {
        "Tecnología": [
            {"title": "Avance en IA Genial",
             "content_text": "Una nueva IA puede escribir código y poemas. Es un gran avance para la humanidad y cambiará todo.",
             "link": "http://example.com/ia", "id": "ia1"},
            {"title": "Python 4.0 Anunciado Oficialmente",
             "content_text": "La Python Software Foundation anuncia Python 4.0 con mejoras en rendimiento y nuevas librerías estándar. La comunidad está expectante.",
             "link": "http://example.com/py4", "id": "py1"}
        ],
        "Deportes": [
            {"title": "Final de Copa Emocionante",
             "content_text": "El equipo local ganó la final en un partido no apto para cardíacos. Hubo goles y mucha tensión hasta el último minuto.",
             "link": "http://example.com/game1", "id": "game1"}
        ]
    }
    # Asegúrate de tener `llm` instalado y un modelo configurado (ej. `llm install llm-gpt4all` y luego `llm -m gpt4all-j Llama-2-7B-Chat-GGML`)
    # O configurar una API key (ej. `llm keys set openai <tu_api_key>`)
    # y ajustar LLM_MODEL_SYNTHESIS en config.py a un modelo disponible.
    # Para prueba sin API real, puedes temporalmente hacer que los modelos en config.py sean alias de un modelo local que tengas.

    if not model_synthesis:
        print("ADVERTENCIA: Modelo de síntesis no cargado. La prueba será limitada.")

    synthesized = synthesize_data(sample_classified_articles)
    for category, items in synthesized.items():
        print(f"\nCategoría Sintetizada: {category}")
        for item in items:
            print(f"  Bloque: {item['text']}")
            if item['references']:
                print("    Referencias:")
                for ref in item['references']:
                    print(f"      [{ref['id']}] {ref['title']} ({ref['url']})")