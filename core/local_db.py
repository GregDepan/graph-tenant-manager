"""
Cache local SQLite — affichage instantané des données Graph (v2.1.8).

Principe (cache-aside) :
1. L'UI affiche IMMÉDIATEMENT le cache local (s'il existe) ;
2. La GUI lance le rafraîchissement Graph en arrière-plan ;
3. À l'arrivée, les données fraîches sont écrites dans le cache et
   re-affichées.

Résultat : plus d'écran vide ni de « ⏳ Chargement... » à chaque clic
d'onglet ou bascule de tenant — les données déjà vues s'affichent en
millisecondes, le rafraîchissement réseau passe derrière.

Design :
- Une base SQLite PAR TENANT : core/cache_dir()/tenant_<guid>.sqlite —
  isolation totale entre clients, suppression simple (supprimer le
  fichier), aucune contention entre tenants.
- Colonnes clé/valeur par table de collection (users/groups/devices/
  licenses) + timestamp : le JSON est déserialisé en dicts au chargement.
- WAL journal mode : lectures concurrentes sûres pendant les écritures
  du thread de rafraîchissement.
- Toutes les opérations sont tolérantes aux fautes : un cache corrompu
  ou absent ne casse JAMAIS l'application (retour [] / None).
- Thread-safety : une connexion par thread n'est pas nécessaire —
  sqlite3 en mode WAL accepte les lectures concurrentes ; les écritures
  passent par un verrou applicatif et retry sur « database is locked ».
"""

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import du cache_dir partagé (même dossier que les tokens MSAL)
from core.auth import cache_dir

_LOCK = threading.Lock()

# Nettoyage d'un GUID pour un nom de fichier sûr
_GUID_RE = re.compile(r"[^A-Za-z0-9\-]")


def _safe_name(tenant_id: str) -> str:
    return _GUID_RE.sub("_", str(tenant_id))[:64] or "unknown"


def _db_path(tenant_id: str) -> Path:
    return cache_dir() / f"tenant_{_safe_name(tenant_id)}.sqlite"


def _connect(tenant_id: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(tenant_id), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS collections (
            name TEXT PRIMARY KEY,
            updated_at REAL NOT NULL,
            payload TEXT NOT NULL
        );
        """
    )
    conn.commit()


def save_collection(tenant_id: str, name: str, items: List[Dict[str, Any]]) -> bool:
    """
    Écrit (ou remplace) une collection d'objets pour un tenant.

    Args:
        tenant_id: GUID du tenant (clé d'isolation de la base)
        name: nom logique de la collection ("users", "groups",
              "devices", "licenses", "portfolio", ...)
        items: liste de dicts sérialisables en JSON

    Returns:
        True si écrit, False si échec (non fatal : l'UI continue
        avec les données réseau).
    """
    if not tenant_id:
        return False
    payload = json.dumps(items, ensure_ascii=False, default=str)
    with _LOCK:
        try:
            conn = _connect(tenant_id)
            try:
                _ensure_tables(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO collections (name, updated_at, payload) "
                    "VALUES (?, ?, ?)",
                    (name, time.time(), payload),
                )
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as e:
            print(f"[Cache] Écriture '{name}' impossible ({e})")
            return False


def load_collection(tenant_id: str, name: str,
                    max_age_hours: Optional[float] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Lit une collection en cache pour un tenant.

    Args:
        max_age_hours: âge maximum accepté (None = illimité). Au-delà,
              la collection est considérée comme absente (retour None) —
              le rafraîchissement réseau reprendra le relais.

    Returns:
        La liste de dicts, ou None si absente/expirée/erreur.
    """
    if not tenant_id:
        return None
    try:
        conn = _connect(tenant_id)
        try:
            row = conn.execute(
                "SELECT updated_at, payload FROM collections WHERE name = ?",
                (name,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        updated_at, payload = row
        if max_age_hours is not None and (time.time() - updated_at) > max_age_hours * 3600:
            return None
        data = json.loads(payload)
        return data if isinstance(data, list) else None
    except Exception as e:
        print(f"[Cache] Lecture '{name}' impossible ({e})")
        return None


def collection_age_seconds(tenant_id: str, name: str) -> Optional[float]:
    """Âge en secondes du dernier rafraîchissement d'une collection (ou None)."""
    if not tenant_id:
        return None
    try:
        conn = _connect(tenant_id)
        try:
            row = conn.execute(
                "SELECT updated_at FROM collections WHERE name = ?", (name,)
            ).fetchone()
        finally:
            conn.close()
        return (time.time() - row[0]) if row else None
    except Exception:
        return None


def drop_tenant_cache(tenant_id: str) -> bool:
    """Supprime la base d'un tenant (déconnexion/réinitialisation)."""
    try:
        path = _db_path(tenant_id)
        if path.exists():
            path.unlink()
        for suffix in ("-wal", "-shm"):
            side = Path(str(path) + suffix)
            if side.exists():
                side.unlink()
        return True
    except Exception as e:
        print(f"[Cache] Suppression impossible ({e})")
        return False


def cache_summary() -> Dict[str, Any]:
    """Infos de debug : bases présentes + tailles (Mo)."""
    out: Dict[str, Any] = {"dbs": [], "total_mb": 0.0}
    try:
        for p in cache_dir().glob("tenant_*.sqlite"):
            size_mb = p.stat().st_size / (1024 * 1024)
            out["dbs"].append({"file": p.name, "mb": round(size_mb, 2)})
            out["total_mb"] += size_mb
    except Exception:
        pass
    return out