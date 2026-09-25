"""
Service métier SharePoint : inventaire des sites du tenant.

Concentre la logique de :
    - listing des sites (SPO, OneDrive persos exclus par défaut)
    - stockage par site (quota/consommé/dispo depuis le drive par défaut)
    - détection des bibliothèques documentaires par site (lazy)
    - export CSV de l'inventaire
"""

import csv
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("GraphTenantManager")

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


# 1 Mo en octets — arrondi lisible pour l'UI et les exports
MB = 1024 * 1024


def _gb(value: Optional[int]) -> str:
    """Formate des octets en Go avec 1 décimale ('' si vide)."""
    if value is None:
        return ""
    try:
        return f"{int(value) / (1024 ** 3):.1f} Go"
    except (TypeError, ValueError):
        return ""


def _fmt_date(value: Any) -> str:
    """ISO 8601 → '25/09/2026' ('' si absent)."""
    if not value:
        return ""
    try:
        s = str(value)
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    except Exception:
        return ""


class SharePointService:
    """
    Service métier pour l'inventaire SharePoint du tenant.

    Contrat d'interface (la GUI code contre cette API) :
        get_sites() -> List[dict]
        get_libraries(site_id) -> List[dict]
        export_to_csv(sites, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        self.graph = graph_wrapper

    # ------------------------------------------------------------------
    # Inventaire des sites
    # ------------------------------------------------------------------

    async def get_sites(self, include_personal: bool = False) -> List[Dict[str, Any]]:
        """
        Récupère l'inventaire des sites SharePoint du tenant.

        Args:
            include_personal: inclut les sites personnels OneDrive
                (isPersonalSite=True) — exclus par défaut car ils sont
                couverts par l'onglet OneDrive.

        Returns:
            Liste triée par nom, dicts avec clés : id, name, url, owner,
            created, last_modified, storage_used, storage_quota,
            personal
        """
        sites = await self.graph.get_all_sites()

        result: List[Dict[str, Any]] = []
        for site in sites:
            if getattr(site, "is_personal_site", None):
                if not include_personal:
                    continue

            site_id = getattr(site, "id", None) or ""
            web_url = getattr(site, "web_url", None) or ""
            display_name = getattr(site, "display_name", None) or \
                (web_url.split("/")[-1] if web_url else "N/A")

            item = {
                "id": site_id,
                "name": display_name,
                "url": web_url,
                "owner": "",
                "created": _fmt_date(getattr(site, "created_date_time", None)),
                "last_modified": _fmt_date(
                    getattr(site, "last_modified_date_time", None)),
                "storage_used": None,
                "storage_quota": None,
                "personal": bool(getattr(site, "is_personal_site", None)),
            }
            result.append(item)

        # Tri alphabétique sur le nom affiché
        result.sort(key=lambda s: (s["name"] or "").lower())
        return result

    # ------------------------------------------------------------------
    # Bibliothèques documentaires d'un site
    # ------------------------------------------------------------------

    async def get_libraries(self, site_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les bibliothèques documentaires (drives) d'un site.

        Args:
            site_id: identifiant du site (ex. callcentercontoso.sharepoint.com,xxx)

        Returns:
            Liste de dicts : id, name, type, storage_used, storage_quota, url
        """
        drives = await self.graph.get_site_drives(site_id)

        result = []
        for drv in drives:
            quota = getattr(drv, "quota", None)
            used = getattr(quota, "used", None) if quota else None
            total = getattr(quota, "total", None) if quota else None
            result.append({
                "id": getattr(drv, "id", None) or "",
                "name": getattr(drv, "name", None) or "N/A",
                "type": getattr(drv, "drive_type", None) or "",
                "storage_used": used,
                "storage_quota": total,
                "url": getattr(drv, "web_url", None) or "",
            })
        return result

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def export_to_csv(self, sites: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte l'inventaire des sites en CSV (point-virgule, Excel FR).

        Args:
            sites: liste de dicts issue de get_sites()
            filepath: chemin du fichier de destination

        Returns:
            True si écrit, False sinon
        """
        if not sites:
            logger.warning("Export CSV sites : aucune donnée")
            return False
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["Site", "URL", "Propriétaire", "Créé le",
                                 "Modifié le", "Stockage utilisé",
                                 "Quota", "Type"])
                for s in sites:
                    writer.writerow([
                        s.get("name", ""),
                        s.get("url", ""),
                        s.get("owner", ""),
                        s.get("created", ""),
                        s.get("last_modified", ""),
                        _gb(s.get("storage_used")),
                        _gb(s.get("storage_quota")),
                        "Perso" if s.get("personal") else "SharePoint",
                    ])
            logger.info("Export sites CSV écrit : %s", filepath)
            return True
        except OSError as exc:
            logger.error("Export CSV sites impossible : %s", exc)
            return False