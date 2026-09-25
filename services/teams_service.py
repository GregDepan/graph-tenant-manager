"""
Service métier Teams : inventaire des équipes et leurs canaux.

Couvre :
    - liste des équipes du tenant (depuis /teams, champs sélection)
    - canaux d'une équipe (standard + privés), à la demande
    - nombre de membres par équipe (à la demande, via $count)
    - export CSV de l'inventaire

Note : l'API /teams liste les équipes dont l'utilisateur connecté est
membre ou propriétaire. Pour un inventaire complet du tenant (MSP), on
bascule sur /groups filtré sur resourceProvisioningOptions=Team : les
groupes habilités Teams sont les équipes — y compris celles où l'admin
connecté n'est pas membre.
"""

import csv
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("GraphTenantManager")

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


def _fmt_date(value: Any) -> str:
    """ISO 8601 → '25/09/2026' ('' si absent)."""
    if not value:
        return ""
    try:
        s = str(value)
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    except Exception:
        return ""


class TeamsService:
    """
    Service métier pour l'inventaire Teams du tenant.

    Contrat d'interface (la GUI code contre cette API) :
        get_all_teams_formatted() -> List[dict]
        get_team_channels(team_id) -> List[dict]
        get_team_member_count(team_id) -> int
        export_to_csv(teams, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        self.graph = graph_wrapper

    # ------------------------------------------------------------------
    # Inventaire des équipes
    # ------------------------------------------------------------------

    async def get_all_teams_formatted(self) -> List[Dict[str, Any]]:
        """
        Récupère toutes les équipes du tenant (via groups + RPO=Team).

        Returns:
            Liste triée par nom, dicts avec clés : id, name, mail,
            visibility, archived, created, description, member_count
            (None au listing : chargé à la demande via
            get_team_member_count)
        """
        teams = await self.graph.get_all_teams()

        result: List[Dict[str, Any]] = []
        for grp in teams:
            group_id = getattr(grp, "id", None) or ""
            if not group_id:
                continue

            mail = getattr(grp, "mail", None) or \
                getattr(grp, "proxy_addresses", None) or ""
            if isinstance(mail, list):
                mail = next((a.split("SMTP:")[1] for a in mail
                             if str(a).upper().startswith("SMTP:")), "")

            result.append({
                "id": group_id,
                "name": getattr(grp, "display_name", None) or "N/A",
                "mail": str(mail or ""),
                "visibility": getattr(grp, "visibility", None) or "",
                "archived": bool(getattr(grp, "is_archived", None)),
                "created": _fmt_date(getattr(grp, "created_date_time", None)),
                "description": getattr(grp, "description", None) or "",
                "member_count": None,
            })

        result.sort(key=lambda t: (t["name"] or "").lower())
        return result

    # ------------------------------------------------------------------
    # Canaux d'une équipe
    # ------------------------------------------------------------------

    async def get_team_channels(self, team_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les canaux d'une équipe.

        Args:
            team_id: identifiant de l'équipe (= id du groupe)

        Returns:
            Liste de dicts : id, name, description, type, email, created
        """
        channels = await self.graph.get_team_channels(team_id)

        result = []
        for ch in channels:
            result.append({
                "id": getattr(ch, "id", None) or "",
                "name": getattr(ch, "display_name", None) or "N/A",
                "description": getattr(ch, "description", None) or "",
                "type": str(getattr(ch, "membership_type", None) or "standard"),
                "email": getattr(ch, "email", None) or "",
                "created": _fmt_date(getattr(ch, "created_date_time", None)),
            })
        return result

    # ------------------------------------------------------------------
    # Membres
    # ------------------------------------------------------------------

    async def get_team_member_count(self, team_id: str) -> int:
        """
        Nombre de membres d'une équipe via GET /teams/{id}/members/$count.

        Args:
            team_id: identifiant de l'équipe

        Returns:
            Nombre de membres, -1 si indisponible
        """
        return await self.graph.get_team_member_count(team_id)

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def export_to_csv(self, teams: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte l'inventaire Teams en CSV (point-virgule, Excel FR).

        Args:
            teams: liste de dicts issue de get_all_teams_formatted()
            filepath: chemin du fichier de destination

        Returns:
            True si écrit, False sinon
        """
        if not teams:
            logger.warning("Export CSV Teams : aucune donnée")
            return False
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["Équipe", "Email", "Visibilité", "Archivée",
                                 "Créée le", "Description"])
                for t in teams:
                    writer.writerow([
                        t.get("name", ""),
                        t.get("mail", ""),
                        t.get("visibility", ""),
                        "Oui" if t.get("archived") else "Non",
                        t.get("created", ""),
                        t.get("description", ""),
                    ])
            logger.info("Export Teams CSV écrit : %s", filepath)
            return True
        except OSError as exc:
            logger.error("Export CSV Teams impossible : %s", exc)
            return False