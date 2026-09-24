"""
Utilitaire de logging pour Graph Tenant Manager
"""

import logging
import os
from datetime import datetime


def setup_logger(log_file: str = None, level: str = 'INFO') -> logging.Logger:
    """
    Configure et retourne un logger
    
    Args:
        log_file: Chemin du fichier de log (optionnel)
        level: Niveau de logging
        
    Returns:
        Logger configuré
    """
    logger = logging.getLogger('GraphTenantManager')
    logger.setLevel(getattr(logging, level.upper()))
    
    # Formateur
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (si fichier spécifié)
    if log_file:
        # Créer le dossier si nécessaire
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# Logger global
logger = setup_logger()
