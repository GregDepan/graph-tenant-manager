"""
Service de gestion des groupes Microsoft Graph.

Couche métier entre la GUI et le wrapper Graph (GraphClientWrapper).

Correctif majeur : l'ancien get_all_groups_formatted chargeait les membres
de CHAQUE groupe à chaque listing (problème N+1 : pour 200 groupes, 200
appels API supplémentaires). Le compte de membres n'est plus calculé au
listing ; la GUI peut le demander à la demande via get_member_count().
"""

import csv
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


def _determine_group_type(group: Any) -> str:
    """
    Détermine le type lisible d'un groupe à partir de ses propriétés Graph.

    Règles :
        - 'Unified' dans group_types => Microsoft 365
        - mail_enabled + security_enabled => groupe de sécurité à messagerie
        - mail_enabled seul => liste de distribution
        - sinon => groupe de sécurité
    """
    group_types = getattr(group, "group_types", None) or []
    mail_enabled = bool(getattr(group, "mail_enabled", False))
    security_enabled = bool(getattr(group, "security_enabled", False))

    if "Unified" in group_types:
        return "Microsoft 365"
    if mail_enabled and security_enabled:
        return "Mail-Enabled Security"
    if mail_enabled:
        return "Distribution"
    return "Security"


class GroupsService:
    """
    Service métier pour la gestion des groupes.

    Contrat d'interface (la GUI code contre cette API) :
        get_all_groups_formatted() -> List[dict]   (sans member_count)
        get_group_members(group_id) -> List[dict]
        get_member_count(group_id) -> int
        create(group_data) -> Optional[str]
        add_member(group_id, member_id) -> bool
        remove_member(group_id, member_id) -> bool
        delete(group_id) -> bool
        export_to_csv(groups, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        """
        Initialise le service.

        Args:
            graph_wrapper: Instance de GraphClientWrapper authentifié
        """
        self.graph = graph_wrapper

    # ==================== LECTURE ====================

    async def get_all_groups_formatted(self) -> List[Dict[str, Any]]:
        """
        Récupère tous les groupes du tenant, formatés pour la GUI.

        Correctif N+1 : PLUS AUCUN appel membres par groupe ici. Le compte
        de membres est disponible séparément via get_member_count().

        Returns:
            Liste de dictionnaires avec les clés : id, display_name, mail,
            mail_enabled, security_enabled, group_type, description
        """
        # limit=None côté wrapper => pagination complète du tenant
        groups = await self.graph.get_all_groups()

        result = []
        for group in groups:
            result.append({
                "id": group.id,
                "display_name": group.display_name or "N/A",
                "mail": group.mail or "",
                "mail_enabled": bool(group.mail_enabled),
                "security_enabled": bool(group.security_enabled),
                "group_type": _determine_group_type(group),
                "description": group.description or "",
            })

        return result

    async def get_group_members(self, group_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les membres d'un groupe, formatés pour la GUI.

        Args:
            group_id: ID du groupe

        Returns:
            Liste de dictionnaires avec les clés : id, display_name, email, type
        """
        members = await self.graph.get_group_members(group_id)

        result = []
        for member in members:
            # Le type OData (ex. '#microsoft.graph.user') distingue
            # utilisateurs, groupes et autres objets directory
            odata_type = str(getattr(member, "odata_type", "") or "").lower()
            if "user" in odata_type:
                member_type = "Utilisateur"
            elif "group" in odata_type:
                member_type = "Groupe"
            else:
                member_type = "Autre"

            email = (
                getattr(member, "mail", None)
                or getattr(member, "user_principal_name", None)
                or ""
            )

            result.append({
                "id": member.id,
                "display_name": getattr(member, "display_name", None) or "N/A",
                "email": email,
                "type": member_type,
            })

        return result

    async def get_member_count(self, group_id: str) -> int:
        """
        Récupère le nombre de membres d'un groupe (à la demande).

        Chargé individuellement par la GUI (ex. lors de la sélection d'un
        groupe), jamais en masse au listing.

        Args:
            group_id: ID du groupe

        Returns:
            Nombre de membres directs (0 si erreur ou groupe vide)
        """
        if not group_id:
            return 0
        try:
            members = await self.graph.get_group_members(group_id)
            return len(members)
        except Exception as e:
            logger.error(f"Erreur get_member_count (groupe {group_id}) : {e}")
            return 0

    # ==================== ÉCRITURE ====================

    async def create(self, group_data: Dict[str, Any]) -> Optional[str]:
        """
        Crée un groupe.

        Args:
            group_data: Dictionnaire (clés camelCase) avec :
                - displayName (requis)
                - mailEnabled (optionnel, False par défaut)
                - securityEnabled (optionnel, True par défaut)
                - groupTypes (optionnel, [] par défaut ; ['Unified'] pour M365)
                - mailNickname (optionnel, déduit du nom si absent)
                - description (optionnel)

        Returns:
            ID du groupe créé, ou None en cas d'échec
        """
        display_name = (group_data.get("displayName") or "").strip()
        if not display_name:
            logger.error("Création groupe impossible : displayName absent.")
            return None

        mail_enabled = bool(group_data.get("mailEnabled", False))
        group_types = group_data.get("groupTypes") or []
        mail_nickname = group_data.get("mailNickname") or display_name.replace(" ", "")

        create_data: Dict[str, Any] = {
            "displayName": display_name,
            "mailEnabled": mail_enabled,
            "securityEnabled": bool(group_data.get("securityEnabled", True)),
            "groupTypes": group_types,
            "mailNickname": mail_nickname,
        }

        if group_data.get("description"):
            create_data["description"] = group_data["description"]

        group = await self.graph.create_group(create_data)
        if group is None:
            logger.error(f"Création groupe échouée côté Graph : {display_name}")
            return None

        logger.info(f"Groupe créé : {display_name} (id={group.id})")
        return group.id

    async def add_member(self, group_id: str, member_id: str) -> bool:
        """
        Ajoute un membre à un groupe.

        Args:
            group_id: ID du groupe
            member_id: ID de l'objet directory (utilisateur ou groupe)

        Returns:
            True si succès
        """
        return await self.graph.add_group_member(group_id, member_id)

    async def remove_member(self, group_id: str, member_id: str) -> bool:
        """
        Supprime un membre d'un groupe.

        Args:
            group_id: ID du groupe
            member_id: ID du membre à retirer

        Returns:
            True si succès
        """
        return await self.graph.remove_group_member(group_id, member_id)

    async def delete(self, group_id: str) -> bool:
        """
        Supprime un groupe.

        Le wrapper n'expose pas de delete_group ; on passe par le client
        Graph brut (même approche que l'implémentation précédente).

        Args:
            group_id: ID du groupe

        Returns:
            True si succès
        """
        try:
            await self.graph.client.groups.by_group_id(group_id).delete()
            logger.info(f"Groupe supprimé : {group_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur suppression groupe {group_id} : {e}")
            return False

    # ==================== EXPORT ====================

    def export_to_csv(self, groups: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte les groupes en CSV (sans member_count, conformément au
        nouveau format de listing).

        Args:
            groups: Liste des groupes (format get_all_groups_formatted)
            filepath: Chemin du fichier de sortie

        Returns:
            True si succès
        """
        try:
            if not groups:
                return False

            fieldnames = [
                "id", "display_name", "mail", "mail_enabled",
                "security_enabled", "group_type", "description",
            ]

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(groups)

            return True
        except Exception as e:
            logger.error(f"Erreur export CSV groupes : {e}")
            return False