import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
# Esto es útil para desarrollo local. En producción (ej. GitHub Actions),
# las variables de entorno se suelen configurar directamente en la plataforma.
dotenv_path = Path(__file__).parent.parent / '.env' # Asume que .env está en la raíz del proyecto (un nivel arriba de src/)
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Cargado .env desde: {dotenv_path}") # Para depuración
else:
    print(f".env no encontrado en: {dotenv_path}") # Para depuración


# Rutas base del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"
HISTORY_DIR = DATA_DIR / "history"
ARCHIVE_DIR = OUTPUT_DIR / "archive"

# Nombres de archivos de configuración
SOURCES_FILE = DATA_DIR / "sources.json"
PREFERENCES_FILE = DATA_DIR / "preferences.json"
PROMPTS_FILE = DATA_DIR / "prompts.json"

# Asegurarse de que los directorios de salida y datos existan
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Configuración de Logging (básico por ahora)
LOG_LEVEL = "INFO" # Ejemplo: DEBUG, INFO, WARNING, ERROR

# Configuración de IA (placeholders)
# En un caso real, podrías usar python-dotenv para cargar esto desde .env
LLM_MODEL_CLASSIFICATION = os.getenv("LLM_MODEL_CLASSIFICATION_ENV") # Ejemplo
LLM_MODEL_RELEVANCE = os.getenv("LLM_MODEL_RELEVANCE_ENV")    # Ejemplo
LLM_MODEL_SYNTHESIS = os.getenv("LLM_MODEL_SYNTHESIS_ENV")   # Ejemplo

# Otros parámetros globales
MAX_ARTICLES_PER_CATEGORY_DEFAULT = int(os.getenv("MAX_ARTICLES_PER_CATEGORY_DEFAULT", 10))
MIN_ARTICLE_LENGTH_DEFAULT = int(os.getenv("MIN_ARTICLE_LENGTH_DEFAULT", 20))

print(f"Usando modelo de clasificación: {LLM_MODEL_CLASSIFICATION}")
print(f"Usando modelo de relevancia: {LLM_MODEL_RELEVANCE}")
print(f"Usando modelo de síntesis: {LLM_MODEL_SYNTHESIS}")