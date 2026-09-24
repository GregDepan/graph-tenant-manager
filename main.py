"""
Graph Tenant Manager v2.0 — Clé en main
Gestion multi-tenants Microsoft 365 sans aucune configuration.

Double-clic sur l'exe (ou python main.py) → bouton « Se connecter » →
navigateur → compte admin du client → le tenant est déduit automatiquement.
"""

import sys
import os

# Chemin de base (script ou exe PyInstaller)
if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_PATH)

import tkinter as tk


def main():
    """Point d'entrée — aucune configuration requise."""
    try:
        from gui.main_window import run_app
    except ImportError as e:
        print(f"❌ Modules introuvables : {e}")
        print("Réinstallez les dépendances : pip install -r requirements.txt")
        input("Appuyez sur Entrée pour fermer...")
        sys.exit(1)

    # Config vide : tout est déduit automatiquement (auth well-known Microsoft).
    # Surcharge optionnelle : config.cfg à côté de l'exe (clientId, scopes...).
    config = load_optional_config()
    run_app(config)


def load_optional_config() -> dict:
    """
    Charge config.cfg s'il existe (toutes les clés optionnelles).
    Absent → dict vide → app well-known Microsoft + scopes par défaut.
    """
    import configparser
    config = {}
    path = os.path.join(BASE_PATH, "config.cfg")
    if not os.path.exists(path):
        return config
    try:
        cp = configparser.ConfigParser()
        cp.read(path, encoding='utf-8')
        config = {
            'clientId': cp.get('azure', 'clientId', fallback='').strip(),
            'graphUserScopes': cp.get('azure', 'graphUserScopes', fallback='').strip(),
            'theme': cp.get('ui', 'theme', fallback='clam'),
            'language': cp.get('ui', 'language', fallback='fr'),
        }
        # clientId vide → well-known Microsoft (ne pas passer de valeur vide)
        if not config['clientId']:
            config.pop('clientId')
        if not config['graphUserScopes']:
            config.pop('graphUserScopes')
        print(f"✓ Configuration chargée depuis {path}")
    except Exception as e:
        print(f"⚠️ config.cfg illisible ({e}) — utilisation des défauts")
        config = {}
    return config


if __name__ == '__main__':
    main()