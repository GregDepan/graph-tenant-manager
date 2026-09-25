"""
Vérification et application automatique des mises à jour GitHub.

Flux :
    1. check_latest_release() interroge l'API GitHub (releases/latest)
       et compare le tag à la version locale (core/app_info.APP_VERSION).
    2. La GUI, au démarrage, appelle check_update() en arrière-plan :
       si une version plus récente existe, une boîte propose la mise à
       jour.
    3. apply_update() télécharge l'asset .exe de la release dans un
       fichier temporaire, puis bascule :
            ancien.exe      → GraphTenantManager.old  (supprimé au
                              prochain lancement s'il traîne)
            nouveau.exe    → ancien.exe (remplacement)
            nouveau.exe    → GraphTenantManager.exe (renommé)
       puis relance le .exe mis à jour.

Tout est en stdlib (urllib, json, os, subprocess) — aucune dépendance.
L'API releases/latest est publique : pas de token nécessaire.

Sous PyInstaller --onefile, l'exe en cours d'exécution est verrouillé
par Windows : on ne peut pas l'écraser, seulement le renommer — c'est
ce que fait le schéma ci-dessus, éprouvé (utilisée par de nombreux
updaters Python).
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from typing import Any, Dict, Optional, Tuple

from core.app_info import (APP_VERSION, EXE_NAME, REPO_NAME, REPO_OWNER,
                           app_version_tuple, parse_version)

logger = logging.getLogger("GraphTenantManager")

API_LATEST = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
DOWNLOAD_TIMEOUT = 120          # secondes — la 1re requête
CHUNK = 1024 * 256             # 256 Ko par bloc de téléchargement


class UpdaterError(Exception):
    """Erreur explicite du mode verbeux (check manuel v2.1.6)."""


def is_frozen() -> bool:
    """True si l'app tourne en .exe PyInstaller."""
    return getattr(sys, "frozen", False)


def exe_path() -> str:
    """Chemin du .exe en cours (mode frozen uniquement)."""
    return os.path.abspath(sys.executable)


def fetch_latest_release(timeout: int = DOWNLOAD_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Interroge releases/latest sur GitHub.

    Returns:
        Dict de la release (tag_name, assets, html_url...) ou None
        (réseau indisponible, rate-limit, JSON invalide...)
    """
    try:
        req = urllib.request.Request(
            API_LATEST,
            headers={
                "User-Agent": "GraphTenantManager-updater",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict) or not data.get("tag_name"):
            return None
        return data
    except Exception as exc:
        logger.info("Mise à jour : API GitHub injoignable (%s)", exc)
        return None


def compare_versions(remote_tag: str) -> Tuple[bool, tuple]:
    """
    Compare le tag de la release distante à la version locale.

    Returns:
        (nouvelle_disponible, version_distante_tuple)
        True seulement si strictement supérieure à la locale.
    """
    remote = parse_version(remote_tag)
    local = app_version_tuple()
    if not remote:
        return False, remote
    # Comparaison par tuples — padding implicite : (2,1) < (2,1,0)
    return remote > local, remote


def check_update(verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Vérifie si une mise à jour est disponible.

    Args:
        verbose: True pour un check MANUEL (menu Aide) — distingue
            « à jour », « injoignable » et « dispo » au lieu de fondre
            les deux premiers dans None (v2.1.6).

    Returns:
        Dict {version, tag, url, exe_asset_url, size} si une release
        plus récente avec un asset .exe existe.
        verbose=False : None sinon (auto-check silencieux au démarrage).
        verbose=True : None si à jour ; lève UpdaterError si injoignable.
    """
    release = fetch_latest_release()
    if release is None:
        if verbose:
            raise UpdaterError(
                "Impossible de contacter GitHub (réseau indisponible, "
                "pare-feu ou limite de débit atteinte)."
            )
        return None

    newer, remote_tuple = compare_versions(release.get("tag_name", ""))
    if not newer:
        if verbose:
            return None  # à jour : le caller affichera la notification
        return None

    # Cherche l'asset .exe de la release
    for asset in release.get("assets", []) or []:
        name = str(asset.get("name", "") or "")
        if name.lower().endswith(".exe") and name.lower() == EXE_NAME.lower():
            return {
                "version": ".".join(str(x) for x in remote_tuple),
                "tag": release.get("tag_name", ""),
                "url": asset.get("browser_download_url", ""),
                "exe_asset_url": asset.get("url", ""),
                "size": asset.get("size", 0),
                "notes": release.get("body", "") or "",
            }
    logger.info("Mise à jour dispo (%s) mais sans asset .exe", release.get("tag_name"))
    if verbose:
        raise UpdaterError(
            f"Une nouvelle version ({release.get('tag_name')}) existe "
            f"mais son fichier .exe n'est pas encore publié."
        )
    return None


def download_update(asset_url: str, progress_cb=None) -> Optional[str]:
    """
    Télécharge l'asset .exe de la release vers un fichier temporaire.

    Args:
        asset_url: browser_download_url de l'asset
        progress_cb: callback optionnel (reçus, total) pour la barre

    Returns:
        Chemin du fichier temporaire téléchargé, None si échec
    """
    req = urllib.request.Request(
        asset_url, headers={"User-Agent": "GraphTenantManager-updater"})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            received = 0
            path = os.path.join(tempfile.mkdtemp(prefix="gtm_update_"),
                                EXE_NAME)
            with open(path, "wb") as fh:
                while True:
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    fh.write(block)
                    received += len(block)
                    if progress_cb and total:
                        progress_cb(received, total)
            if received == 0:
                logger.error("Mise à jour : téléchargement vide")
                return None
            return path
    except Exception as exc:
        logger.error("Mise à jour : téléchargement impossible (%s)", exc)
        return None


def cleanup_stale_old() -> None:
    """
    Supprime un GraphTenantManager.old éventuel d'une mise à jour
    précédente (le fichier était verrouillé au moment du renommage).
    """
    if not is_frozen():
        return
    old = os.path.join(os.path.dirname(exe_path()), "GraphTenantManager.old")
    try:
        if os.path.exists(old):
            os.remove(old)
            logger.info("Mise à jour : ancien binaire .old supprimé")
    except OSError as exc:
        logger.info("Mise à jour : .old non supprimable (%s)", exc)


def apply_update(downloaded_exe: str) -> bool:
    """
    Remplace le binaire courant par la version téléchargée puis relance.

    Schéma (le binaire courant est verrouillé par Windows, on ne peut
    que le renommer) :
        courant.exe → GraphTenantManager.old
        téléchargé  → courant.exe (copie)
        relance du nouvel exe
    """
    if not is_frozen():
        logger.info("Mise à jour ignorée : mode script (pas un .exe)")
        return False

    current = exe_path()
    old = os.path.join(os.path.dirname(current), "GraphTenantManager.old")

    try:
        # 1. courant → .old (verrou Windows : le renommage reste permis)
        if os.path.exists(old):
            os.remove(old)
        os.rename(current, old)
    except OSError as exc:
        logger.error("Mise à jour : renommage impossible (%s)", exc)
        return False

    try:
        # 2. téléchargé → courant
        with open(downloaded_exe, "rb") as src, open(current, "wb") as dst:
            while True:
                block = src.read(CHUNK)
                if not block:
                    break
                dst.write(block)
    except OSError as exc:
        # restauration d'urgence
        try:
            if not os.path.exists(current):
                os.rename(old, current)
        except OSError:
            pass
        logger.error("Mise à jour : copie impossible (%s)", exc)
        return False

    # 3. relance du nouvel exe et fermeture de l'ancien process
    try:
        subprocess.Popen([current], cwd=os.path.dirname(current),
                         close_fds=True)
    except OSError as exc:
        logger.error("Mise à jour : relance impossible (%s)", exc)
        # l'app reste sur l'ancienne version — mais elle fonctionne
        return True

    sys.exit(0)  # jamais atteint — sys.exit lève SystemExit