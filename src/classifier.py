import json
import logging
import llm  # <--- AÑADIDO
from .. import config

logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# --- Carga de Configuraciones ---
_preferences_cache = None
_prompts_cache = None


def get_preferences():
    global _preferences_cache
    if _preferences_cache is None:
        try:
            with open(config.PREFERENCES_FILE, 'r', encoding='utf-8') as f:  # Corrección aquí
                _preferences_cache = json.load(f)
        except FileNotFoundError:
            logger.error(f"Archivo de preferencias no encontrado: {config.PREFERENCES_FILE}")
            _preferences_cache = {}
        except json.JSONDecodeError:
            logger.error(f"Error decodificando el archivo JSON de preferencias: {config.PREFERENCES_FILE}")
            _preferences_cache = {}
    return _preferences_cache


def get_prompts():
    global _prompts_cache
    if _prompts_cache is None:
        try:
            with open(config.PROMPTS_FILE, 'r', encoding='utf-8') as f:
                _prompts_cache = json.load(f)
        except FileNotFoundError:
            logger.error(f"Archivo de prompts no encontrado: {config.PROMPTS_FILE}")
            _prompts_cache = {}  # Devolver un dict vacío para evitar errores NoneType
        except json.JSONDecodeError:
            logger.error(f"Error decodificando el archivo JSON de prompts: {config.PROMPTS_FILE}")
            _prompts_cache = {}
    return _prompts_cache


# --- Modelos de IA ---
try:
    model_classification = llm.get_model(config.LLM_MODEL_CLASSIFICATION)
    model_relevance = llm.get_model(config.LLM_MODEL_RELEVANCE)
    # Configurar timeouts si es necesario, ej: model_classification.options.timeout = 30
except Exception as e:
    logger.error(f"Error al cargar modelos LLM: {e}. Las funciones de IA no operarán correctamente.")
    model_classification = None
    model_relevance = None


# --- Nivel 1: Filtrado rápido basado en reglas ---
def filter_by_rules(article, global_prefs, source_prefs):
    content_to_check = (article['title'] + " " + article['content_text'][:150]).lower()

    for keyword in global_prefs.get('blacklist_keywords_global', []):
        if keyword.lower() in content_to_check:
            logger.info(f"Filtrado por blacklist global (keyword: {keyword}): {article['title']}")
            return False

    for keyword in article.get('source_blacklist', []):
        if keyword.lower() in content_to_check:
            logger.info(f"Filtrado por blacklist de fuente (keyword: {keyword}): {article['title']}")
            return False

    min_len = global_prefs.get('min_article_length_chars', config.MIN_ARTICLE_LENGTH_DEFAULT)
    if len(article['content_text']) < min_len:
        logger.info(f"Filtrado por longitud mínima ({len(article['content_text'])} < {min_len}): {article['title']}")
        return False

    source_keywords = article.get('source_keywords', [])
    if source_keywords:
        matched_source_keyword = False
        for keyword in source_keywords:
            if keyword.lower() in content_to_check:
                matched_source_keyword = True
                break
        if not matched_source_keyword:
            logger.info(f"Filtrado por no coincidir con keywords de fuente: {article['title']}")
            return False
    return True


# --- Nivel 2: Clasificación con IA optimizada ---
def classify_article_ia(article, categories_list, default_category):
    if not model_classification:
        logger.warning("Modelo de clasificación no disponible. Usando categoría por defecto.")
        return default_category

    prompts = get_prompts()
    prompt_template = prompts.get("classification", {}).get("default")
    if not prompt_template:
        logger.error("No se encontró la plantilla de prompt para clasificación. Usando categoría por defecto.")
        return default_category

    title = article['title']
    short_content = article['content_text'][
                    :get_preferences().get('global', {}).get('max_chars_for_classification_check', 150)]

    prompt = prompt_template.format(
        categories_list=", ".join(f"'{c}'" for c in categories_list),  # Enviar como una lista de strings
        title=title,
        short_content=short_content,
        default_category=default_category
    )

    logger.info(f"Clasificando artículo (IA): {title[:50]}...")
    try:
        response = model_classification.prompt(prompt)
        predicted_category = response.text().strip().replace("'", "").replace('"', '')  # Limpiar comillas

        if predicted_category in categories_list:
            logger.info(f"Artículo '{title[:50]}' clasificado como '{predicted_category}' por IA.")
            return predicted_category
        else:
            logger.warning(
                f"IA devolvió categoría no válida ('{predicted_category}') para '{title[:50]}'. Usando default: '{default_category}'. Respuesta LLM: {response.text()}")
            return default_category
    except Exception as e:
        logger.error(f"Error en llamada a LLM para clasificación de '{title[:50]}': {e}. Usando default.")
        return default_category


# --- Nivel 2: Evaluación de relevancia con IA ---
def check_relevance_ia(article, category):
    if not model_relevance:
        logger.warning("Modelo de relevancia no disponible. Asumiendo relevante si pasa filtros básicos.")
        return True  # O False, dependiendo de la política de fallback deseada

    prefs = get_preferences()
    prompts = get_prompts()

    prompt_base_template = prompts.get("relevance", {}).get("base")
    criteria_templates = prompts.get("relevance", {}).get("criteria_templates", {})
    no_specific_criteria_text = prompts.get("relevance", {}).get("no_specific_criteria",
                                                                 "No hay criterios específicos.")

    if not prompt_base_template:
        logger.error("No se encontró la plantilla base de prompt para relevancia. Asumiendo relevante.")
        return True

    category_prefs = prefs.get('categories', {}).get(category, {})
    title = article['title']
    short_content = article['content_text'][:prefs.get('global', {}).get('max_chars_for_relevance_check', 300)]

    # Construir el texto de criterios
    criteria_text_parts = []
    category_criteria_template = criteria_templates.get(category, criteria_templates.get("General"))

    if category_criteria_template:
        # Sustituir placeholders en la plantilla de criterios
        # Ejemplo: teams_of_interest, topics_of_interest, etc.
        # Esto requiere que los nombres de las claves en category_prefs coincidan con los placeholders
        try:
            formatted_criteria = category_criteria_template.format(**category_prefs)
            criteria_text_parts.append(formatted_criteria)
        except KeyError as e:
            logger.warning(
                f"Falta la clave '{e}' en preferences.json para formatear criterios de relevancia de '{category}'. Usando texto genérico.")
            criteria_text_parts.append(no_specific_criteria_text)
    else:
        criteria_text_parts.append(no_specific_criteria_text)

    final_criteria_text = "\n".join(criteria_text_parts)

    prompt = prompt_base_template.format(
        category=category,
        criteria_text=final_criteria_text,
        title=title,
        short_content=short_content
    )

    logger.info(f"Evaluando relevancia (IA) para '{title[:50]}' en '{category}'...")
    try:
        response = model_relevance.prompt(prompt)
        answer = response.text().strip().lower()
        logger.info(f"Respuesta '{answer}'.")
        if answer == 'sí' or answer == 'si':
            logger.info(f"Artículo '{title[:50]}' es RELEVANTE para '{category}' según IA.")
            return True
        elif answer == 'no':
            logger.info(f"Artículo '{title[:50]}' NO es relevante para '{category}' según IA.")
            return False
        else:
            logger.warning(
                f"IA devolvió respuesta no válida ('{answer}') para relevancia de '{title[:50]}'. Asumiendo no relevante. Respuesta LLM: {response.text()}")
            return False  # Fallback a no relevante si la respuesta no es clara
    except Exception as e:
        logger.error(f"Error en llamada a LLM para relevancia de '{title[:50]}': {e}. Asumiendo no relevante.")
        return False


def classify_and_filter_articles(articles):
    prefs = get_preferences()
    global_prefs = prefs.get('global', {})
    defined_categories = global_prefs.get("categories_order", list(prefs.get("categories", {}).keys()))
    logger.info(defined_categories)
    if not defined_categories:  # Fallback si no hay categorías definidas
        defined_categories = ["General"]
        logger.info("No se encontraron 'categories_order' o 'categories' en preferences.json. Usando 'General'.")

    classified_articles = {cat: [] for cat in defined_categories}
    # Asegurar que 'General' exista si es la única categoría o fallback
    if "General" not in classified_articles and "General" in defined_categories:
        classified_articles["General"] = []

    num_filtered_rules = 0
    num_filtered_relevance = 0
    num_processed = 0

    for article in articles:
        num_processed += 1
        if not filter_by_rules(article, global_prefs, prefs.get('sources', {}).get(article['source_name'], {})):
            logger.info(article['title'])
            num_filtered_rules += 1
            continue

        default_cat_for_article = article.get('default_category',
                                              defined_categories[0] if defined_categories else "General")
        assigned_category = classify_article_ia(article, defined_categories, default_cat_for_article)
        article['assigned_category'] = assigned_category

        # Asegurar que la categoría exista en classified_articles antes de la comprobación de relevancia
        if assigned_category not in classified_articles:
            # Esto puede pasar si la IA devuelve una categoría que no estaba en la lista inicial
            # (aunque el prompt intenta evitarlo) o si la default_category no estaba.
            logger.warning(
                f"Categoría '{assigned_category}' asignada por IA no estaba en la lista predefinida. Añadiéndola.")
            classified_articles[assigned_category] = []
            # Opcionalmente, podrías añadirla a defined_categories si quieres que aparezca en la salida
            # aunque no estuviera en el orden original.
            # if assigned_category not in defined_categories:
            # defined_categories.append(assigned_category)

        if not check_relevance_ia(article, assigned_category):
            logger.debug(
                f"Artículo '{article['title'][:50]}' (cat: {assigned_category}) filtrado por irrelevancia (IA).")
            num_filtered_relevance += 1
            continue

        max_articles_cat = prefs.get('categories', {}).get(assigned_category, {}).get('max_articles_per_category',
                                                                                      global_prefs.get(
                                                                                          'max_articles_per_category',
                                                                                          config.MAX_ARTICLES_PER_CATEGORY_DEFAULT))

        if len(classified_articles.get(assigned_category, [])) < max_articles_cat:
            classified_articles.setdefault(assigned_category, []).append(article)
        else:
            logger.debug(f"Categoría '{assigned_category}' llena. Descartando: {article['title'][:50]}")

    logger.info(f"Procesados: {num_processed} artículos.")
    logger.info(f"Filtrados por reglas (Nivel 1): {num_filtered_rules}")
    logger.info(f"Filtrados por irrelevancia (Nivel 2 IA): {num_filtered_relevance}")
    for cat, arts in classified_articles.items():
        if arts:  # Solo mostrar categorías con artículos
            logger.info(f"Artículos finales en '{cat}': {len(arts)}")

    # Filtrar categorías vacías del resultado final si se desea
    return {cat: arts for cat, arts in classified_articles.items() if arts}


if __name__ == '__main__':
    from .collector import collect_all_articles

    sample_articles = collect_all_articles()
    if sample_articles:
        classified = classify_and_filter_articles(sample_articles)
        for category, articles_in_category in classified.items():
            if articles_in_category:
                print(f"\nCategoría: {category}")
                for art in articles_in_category:
                    print(f"  - {art['title']}")