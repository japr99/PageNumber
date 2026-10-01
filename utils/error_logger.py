"""
Logger minimalista para capturar errores críticos en PageNumber.
Solo registra excepciones reales, sin warnings de comportamiento normal.
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform


def get_log_path():
    """Obtiene la ruta del archivo de log en la carpeta de preferencias."""
    if platform.system() == "Darwin":  # macOS
        app_support = Path.home() / "Library" / "Application Support" / "PageNumber"
    elif platform.system() == "Windows":
        app_support = Path(os.environ.get("APPDATA", "")) / "PageNumber"
    else:  # Linux
        app_support = Path.home() / ".config" / "PageNumber"
    
    app_support.mkdir(parents=True, exist_ok=True)
    return app_support / "pagenumber_errors.log"


class FontToolsWarningFilter(logging.Filter):
    """Filtra warnings irrelevantes de fontTools"""
    
    IGNORED_PATTERNS = [
        "extra bytes in post.stringData array",
        "timestamp seems very low; regarding as unix timestamp",
    ]
    
    def filter(self, record):
        """Retorna False para mensajes que deben descartarse"""
        if record.levelno == logging.WARNING:
            message = record.getMessage()
            for pattern in self.IGNORED_PATTERNS:
                if pattern in message:
                    return False  # Descartar este mensaje
        return True  # Permitir todos los demás


def setup_error_logger():
    """
    Configura el logger de errores.
    Captura WARNING, ERROR y CRITICAL, con rotación automática.
    Configura el root logger para que todos los logging.error/warning/critical funcionen.
    """
    log_file = get_log_path()
    
    # Configurar el ROOT logger para capturar todos los logging.error() del código
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # WARNING, ERROR y CRITICAL
    
    # Evitar duplicados si ya está configurado
    if root_logger.handlers:
        # Limpiar handlers existentes para evitar duplicados
        root_logger.handlers.clear()
    
    # Handler con rotación: máximo 3 archivos de 2MB
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,  # 2MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.WARNING)  # Solo WARNING+
    
    # Añadir filtro para descartar warnings irrelevantes de fontTools
    file_handler.addFilter(FontToolsWarningFilter())
    
    # Formato: timestamp | nivel | mensaje
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # TAMBIÉN añadir handler para consola (desarrollo)
    # Solo si sys.stderr existe (no en exe con console=False)
    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.ERROR)  # Solo ERROR y CRITICAL en consola
        console_handler.addFilter(FontToolsWarningFilter())
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Escribir cabecera inicial directamente al archivo para confirmar funcionamiento
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]  # Formato con milisegundos
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"PageNumber iniciado - {timestamp}\n")
        f.write(f"{'='*60}\n")
    
    return root_logger


def log_exception(exc_type, exc_value, exc_traceback):
    """
    Handler para excepciones no capturadas.
    Se registra automáticamente con sys.excepthook.
    """
    # Ignorar KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger = logging.getLogger()  # Root logger
    logger.critical(
        "Excepción no capturada",
        exc_info=(exc_type, exc_value, exc_traceback)
    )
    # También dejar que la traza aparezca en stderr para desarrollo
    try:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    except Exception:
        pass


def install_exception_handler():
    """Instala el handler de excepciones no capturadas."""
    sys.excepthook = log_exception


# Función de conveniencia para logging manual
def log_error(message, exc_info=None):
    """
    Registra un error manualmente.
    
    Args:
        message: Mensaje del error
        exc_info: Tupla (exc_type, exc_value, exc_traceback) o True para capturar automáticamente
    """
    logger = logging.getLogger()  # Root logger
    logger.error(message, exc_info=exc_info)
