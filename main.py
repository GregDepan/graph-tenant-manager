"""
Graph Tenant Manager v2.0 — Clé en main
Gestion multi-tenants Microsoft 365 sans aucune configuration.

Double-clic sur l'exe (ou python main.py) → bouton « Se connecter » →
navigateur → compte admin du client → le tenant est déduit automatiquement.
"""

import sys
import os
import traceback

# Chemin de base (script ou exe PyInstaller)
if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_PATH)

import tkinter as tk

CRASH_LOG = os.path.join(BASE_PATH, "GTM_CRASH.log")


def _report_startup_crash(exc: BaseException) -> None:
    """
    v2.1.9 : rapport de crash de démarrage robuste — le traceback
    complet dans GTM_CRASH.log à côté de l'exe (les métadonnées de
    packages absentes sous PyInstaller crashaient SILENCIEUSEMENT :
    MessageBox native puis « EXE tourne — OK » dans la CI).

    En mode fenêtré il n'y a NI console NI stdin : l'ancien print() +
    input() levait RuntimeError: lost sys.stdin et masquait la vraie
    erreur. Ici : fichier de log toujours + MessageBox si Tkinter
    répond, sinon ExitCode 1.
    """
    tb = traceback.format_exc()
    try:
        with open(CRASH_LOG, "w", encoding="utf-8") as fh:
            fh.write(f"GraphTenantManager n'a pas pu démarrer.\n\n{tb}\n")
    except Exception:
        pass  # répertoire en lecture seule : tant pis pour le log
    try:
        import tkinter.messagebox as _mb
        r = tk.Tk()
        r.withdraw()
        _mb.showerror(
            "Graph Tenant Manager — erreur au démarrage",
            "L'application n'a pas pu démarrer.\n\n"
            f"Détails : {CRASH_LOG}\n\n"
            f"Résumé : {exc}",
        )
        r.destroy()
    except Exception:
        pass  # pas même Tkinter : le exit code suffira


def main():
    """Point d'entrée — aucune configuration requise."""
    # v2.1.9 : mode smoke test CI (GTM_SMOKE=1) — importe les modules
    # critiques (msgraph/azure → déclenche les importlib.metadata qui
    # plantent si PyInstaller n'a pas embarqué les métadonnées) puis
    # s'arrête proprement. La CI vérifie la présence de GTM_SMOKE_OK.txt.
    if os.environ.get("GTM_SMOKE") == "1":
        try:
            from gui.main_window import run_app  # noqa: F401 (import)
            import msgraph  # noqa: F401
            import azure.identity  # noqa: F401
            import core.updater  # noqa: F401
        except BaseException as e:
            _report_startup_crash(e)
            sys.exit(1)
        with open(os.path.join(BASE_PATH, "GTM_SMOKE_OK.txt"), "w") as fh:
            fh.write("imports OK\n")
        sys.exit(0)

    # v2.1.9 : TOUTES les erreurs de démarrage sont attrapées (pas
    # seulement ImportError — les crashes de métadonnées PyInstaller
    # sont des PackageNotFoundError, et un hook d'import peut lever
    # n'importe quoi). Rapport : GTM_CRASH.log + MessageBox.
    try:
        from gui.main_window import run_app
    except BaseException as e:
        _report_startup_crash(e)
        sys.exit(1)

    # Config vide : tout est déduit automatiquement (auth well-known Microsoft).
    # Surcharge optionnelle : config.cfg à côté de l'exe (clientId, scopes...).
    config = load_optional_config()

    # v2.1 : supprime un éventuel GraphTenantManager.old d'une mise à jour
    # précédente (le fichier était verrouillé au moment du renommage).
    try:
        from core.updater import cleanup_stale_old
        cleanup_stale_old()
    except Exception:
        pass  # jamais bloquant

    # v2.1.9 : un crash pendant l'initialisation de l'interface ne doit
    # pas non plus partir en RuntimeError: lost sys.stdin.
    try:
        run_app(config)
    except BaseException as e:
        _report_startup_crash(e)
        sys.exit(1)


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
    except Exception:
        config = {}
    return config


if __name__ == '__main__':
    main()