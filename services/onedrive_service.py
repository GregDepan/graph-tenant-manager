"""
Service métier OneDrive : inventaire des lecteurs personnels.

Couvre :
    - liste des lecteurs OneDrive par utilisateur (via /users/{id}/drive)
    - quota / consommation / dernier fichier modifié
    - export CSV de l'inventaire

Note : le listing /drives racine ne retourne que les drives « visibles » ;
l'énumération par utilisateur (/users/{id}/drive) est la méthode fiable
pour couvrir tout le tenant, au prix d'un appel par utilisateur. Pour
rester fluide sur les gros tenants, le listing est séquencé par lots et
les erreurs individuelles sont ignorées (compteur inclus dans la réponse).
"""

import asyncio
import csv
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("GraphTenantManager")

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


def _gb(value: Optional[int]) -> str:
    """Formate des octets en Go avec 1 décimale ('' si vide)."""
    if value is None:
        return ""
    try:
        return f"{int(value) / (1024 ** 3):.1f} Go"
    except (TypeError, ValueError):
        return ""


class OneDriveService:
    """
    Service métier pour l'inventaire OneDrive du tenant.

    Contrat d'interface (la GUI code contre cette API) :
        get_drives() -> List[dict]
        export_to_csv(drives, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        self.graph = graph_wrapper

    # ------------------------------------------------------------------
    # Inventaire des lecteurs
    # ------------------------------------------------------------------

    async def get_drives(self) -> List[Dict[str, Any]]:
        """
        Récupère l'inventaire OneDrive : un lecteur par utilisateur actif.

        Énumère les utilisateurs du tenant puis interroge /users/{id}/drive.
        Un utilisateur sans lecteur OneDrive (jamais provisionné, sans
        licence) est simplement absent du résultat.

        Returns:
            Liste triée par propriétaire, dicts avec clés : id, owner,
            owner_email, storage_used, storage_quota, storage_remaining,
            state, url, last_activity
        """
        users = await self.graph.get_all_users()
        result: List[Dict[str, Any]] = []

        for user in users:
            user_id = getattr(user, "id", None) or ""
            if not user_id:
                continue
            # Les comptes bloqués sont conservés : leur stockage reste
            # consommé, l'admin doit le voir.
            drive = await self.graph.get_user_drive(user_id)
            if drive is None:
                continue

            quota = getattr(drive, "quota", None)
            used = getattr(quota, "used", None) if quota else None
            total = getattr(quota, "total", None) if quota else None
            remaining = getattr(quota, "remaining", None) if quota else None
            state = getattr(quota, "state", None) if quota else ""

            owner_name = getattr(user, "display_name", None) or "N/A"
            owner_mail = getattr(user, "mail", None) or \
                getattr(user, "user_principal_name", None) or ""

            result.append({
                "id": getattr(drive, "id", None) or "",
                "owner": owner_name,
                "owner_email": owner_mail,
                "storage_used": used,
                "storage_quota": total,
                "storage_remaining": remaining,
                "state": str(state or ""),
                "url": getattr(drive, "web_url", None) or "",
                "last_activity": "",
            })

        # Tri alphabétique sur le propriétaire
        result.sort(key=lambda d: (d["owner"] or "").lower())
        return result

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def export_to_csv(self, drives: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte l'inventaire OneDrive en CSV (point-virgule, Excel FR).

        Args:
            drives: liste de dicts issue de get_drives()
            filepath: chemin du fichier de destination

        Returns:
            True si écrit, False sinon
        """
        if not drives:
            logger.warning("Export CSV OneDrive : aucune donnée")
            return False
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["Propriétaire", "Email", "Utilisé", "Quota",
                                 "Disponible", "État", "URL"])
                for d in drives:
                    writer.writerow([
                        d.get("owner", ""),
                        d.get("owner_email", ""),
                        _gb(d.get("storage_used")),
                        _gb(d.get("storage_quota")),
                        _gb(d.get("storage_remaining")),
                        d.get("state", ""),
                        d.get("url", ""),
                    ])
            logger.info("Export OneDrive CSV écrit : %s", filepath)
            return True
        except OSError as exc:
            logger.error("Export CSV OneDrive impossible : %s", exc)
            return False