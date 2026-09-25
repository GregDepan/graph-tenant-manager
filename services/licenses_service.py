"""
Service de gestion des licences Microsoft 365 (NOUVEAU).

Couche métier entre la GUI et le wrapper Graph (GraphClientWrapper) :
  - Inventaire des SKUs souscrits par le tenant (get_inventory)
  - Utilisateurs sans licence (get_unlicensed_users)

Le wrapper expose get_subscribed_skus() -> List[SubscribedSku] avec les
champs : sku_id, sku_part_number, consumed_units, prepaid_units
(liste d'objets avec enabled).
"""

import csv
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper

from services.users_service import _format_user


# =====================================================================
# Mapping SKU part number -> nom commercial français
# Fallback : le part number est retourné tel quel.
# =====================================================================
SKU_DISPLAY_NAMES: Dict[str, str] = {
    # Microsoft 365 (offre moderne)
    "SPE_E3": "Microsoft 365 E3",
    "SPE_E5": "Microsoft 365 E5",
    "SPE_F1": "Microsoft 365 F1",
    "SPE_F3": "Microsoft 365 F3",
    "M365_F3": "Microsoft 365 F3",
    "SPE_E1": "Microsoft 365 E1",
    "SPB": "Microsoft 365 Business Premium",
    "CBA": "Microsoft 365 Business Basic",
    "O365_BUSINESS_ESSENTIALS": "Office 365 Business Essentials",
    "O365_BUSINESS_PREMIUM": "Office 365 Business Premium",
    "O365_BUSINESS": "Office 365 Business",
    "O365_BUSINESS_ESSENTIALS": "Office 365 Business Essentials",
    # Office 365 (offre historique entreprise)
    "STANDARDPACK": "Office 365 Enterprise E1",
    "ENTERPRISEPACK": "Office 365 E3",
    "ENTERPRISEPREMIUM": "Office 365 E5",
    "ENTERPRISEPREMIUM_NOPSTNCONF": "Office 365 E5 (sans audioconf.)",
    "DESKLESSPACK": "Office 365 F3",
    "EXCHANGESTANDARD": "Exchange Online Plan 2",
    "EXCHANGEDESKTOP": "Exchange Online Plan 1",
    "EXCHANGEARCHIVE_ADDON": "Exchange Online Archiving",
    "EXCHANGEESSENTIALS": "Exchange Online Essentials",
    "EXCHANGE_S_ESSENTIALS": "Exchange Online Essentials",
    # Sécurité / mobilité / identité
    "EMS": "Enterprise Mobility + Security E3",
    "EMSPREMIUM": "Enterprise Mobility + Security E5",
    "AAD_PREMIUM": "Entra ID P1",
    "AAD_PREMIUM_P2": "Entra ID P2",
    "AAD_PREMIUM_FREE": "Entra ID Free",
    "IDENTITY_THREAT_PROTECTION": "Microsoft Defender pour Identity",
    "IDENTITY_THREAT_PROTECTION_FOR_ENTRA_P2": "Defender pour Identity (P2)",
    "MICROSOFT_BUSINESS_CENTER": "Microsoft Business Center",
    "M365_LIGHTWEIGHT": "Microsoft 365 F3 (lightweight)",
    "STREAM": "Microsoft Stream",
    "POWER_BI_PRO": "Power BI Pro",
    "POWER_BI_STANDARD": "Power BI (gratuit)",
    "PROJECTPROFESSIONAL": "Project Plan 3",
    "PROJECTPREMIUM": "Project Plan 5",
    "PROJECTESSENTIALS": "Project Plan 1",
    "VISIOCLIENT": "Visio Plan 2",
    "VISIOPRO": "Visio Plan 2",
    "WIN10_PRO_ENT_SUB": "Windows 10/11 Enterprise",
    "WINDOWS_STORE": "Windows Store pour entreprises",
    "DYN365_ENTERPRISE_SALES": "Dynamics 365 Sales Enterprise",
    "DYN365_ENTERPRISE_CUSTOMER_SERVICE": "Dynamics 365 Customer Service Ent.",
    "DYN365_FINANCIALS": "Dynamics 365 Finance",
    "MCOCA": "Microsoft Teams Phone",
    "MCOMEETADV": "Microsoft 365 Audioconférence",
    "TEAMS_EXPLORATORY": "Microsoft Teams Exploratory",
    "Microsoft_Teams_Exploratory": "Microsoft Teams Exploratory",
    "CRMSTANDARD": "Dynamics CRM Online",
    "FLOW_FREE": "Power Automate (gratuit)",
    "POWERAPPS_VIRAL": "Power Apps (essai)",
    "SPZA": "App Source",
    "SPB_INDIVIDUAL": "Microsoft 365 Business (individuel)",
    "LITE": "Microsoft 365 F1 (lite)",
    "DESKLESSPACK_FACULTY": "Office 365 F3 (enseignants)",
    "STANDARD_WOFFPACK_FACULTY": "Office 365 A1 (enseignants)",
    "STUDENT": "Office 365 A1 (étudiants)",
}


def _sku_display_name(part_number: Optional[str]) -> str:
    """
    Retourne le nom commercial français d'un SKU.

    Args:
        part_number: SKU part number (ex. 'SPE_E3')

    Returns:
        Nom mappé si connu, sinon le part_number tel quel ('' si None)
    """
    if not part_number:
        return ""
    return SKU_DISPLAY_NAMES.get(part_number, part_number)


def _total_enabled_units(prepaid_units: Any) -> int:
    """
    Calcule le total d'unités achetées du SKU.

    Dans le SDK Graph, `subscribedSku.prepaidUnits` est un OBJET UNIQUE
    LicenseUnitsDetail (champ `enabled`), PAS une liste — l'itération
    provoquait un TypeError avec de vraies données Microsoft (v1.1-v2.1).

    Args:
        prepaid_units: objet LicenseUnitsDetail (ou None/mock ancien
            format liste, toléré pour compatibilité)

    Returns:
        Nombre d'unités activées (0 si vide/invalide)
    """
    if not prepaid_units:
        return 0
    # Format SDK actuel : objet unique avec champ enabled
    if hasattr(prepaid_units, "enabled"):
        try:
            return int(getattr(prepaid_units, "enabled", 0) or 0)
        except (TypeError, ValueError):
            return 0
    # Tolérance ancien format (séquence d'objets) — mocks v1.x
    try:
        return sum(int(getattr(u, "enabled", 0) or 0) for u in prepaid_units)
    except (TypeError, ValueError):
        return 0


def _compute_warning(total: int, consumed: int, available: int) -> bool:
    """
    Détermine si un SKU doit être signalé comme sous tension (alerte stock).

    Règles (au moins une suffit) :
        - available <= 2 (il ne reste presque plus de licences libres)
        - ratio consommé/total >= 95% (soit available/total <= 5%)

    Args:
        total: Unités achetées
        consumed: Unités consommées
        available: Unités disponibles

    Returns:
        True si alerte
    """
    if available <= 2:
        return True
    if total > 0 and (consumed / total) >= 0.95:
        return True
    return False


class LicensesService:
    """
    Service métier pour l'inventaire des licences du tenant.

    Contrat d'interface (la GUI code contre cette API) :
        get_inventory() -> List[dict]
        get_unlicensed_users() -> List[dict]
        export_to_csv(inventory, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        """
        Initialise le service.

        Args:
            graph_wrapper: Instance de GraphClientWrapper authentifié
        """
        self.graph = graph_wrapper

    # ==================== LECTURE ====================

    async def get_inventory(self) -> List[Dict[str, Any]]:
        """
        Récupère l'inventaire des licences souscrites par le tenant.

        Returns:
            Liste de dictionnaires (triée par nom affiché) avec les clés :
            sku_id, part_number, display_name, total, consumed, available,
            warning
        """
        skus = await self.graph.get_subscribed_skus()

        result = []
        for sku in skus:
            sku_id = getattr(sku, "sku_id", None) or ""
            part_number = getattr(sku, "sku_part_number", None) or ""
            total = _total_enabled_units(getattr(sku, "prepaid_units", None))
            try:
                consumed = int(getattr(sku, "consumed_units", 0) or 0)
            except (TypeError, ValueError):
                consumed = 0
            available = total - consumed

            result.append({
                "sku_id": sku_id,
                "part_number": part_number,
                "display_name": _sku_display_name(part_number),
                "total": total,
                "consumed": consumed,
                "available": available,
                "warning": _compute_warning(total, consumed, available),
            })

        # Tri alphabétique sur le nom affiché pour un listing stable
        result.sort(key=lambda item: (item["display_name"] or "").lower())
        return result

    async def get_unlicensed_users(self) -> List[Dict[str, Any]]:
        """
        Récupère les utilisateurs du tenant ne disposant d'aucune licence.

        Format identique à UsersService.get_all_users_formatted(), filtré
        sur has_license=False.

        Returns:
            Liste de dictionnaires utilisateurs sans licence
        """
        # Pagination complète puis filtrage local : le filtre Graph
        # 'assignedLicenses/$count eq 0' exige ConsistencyLevel eventual
        # et reste peu fiable ; on réutilise le formatage éprouvé.
        users = await self.graph.get_all_users()

        result = []
        for user in users:
            assigned = getattr(user, "assigned_licenses", None) or []
            if assigned:
                continue  # l'utilisateur a au moins une licence
            result.append(_format_user(user))

        return result

    # ==================== EXPORT ====================

    def export_to_csv(self, inventory: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte l'inventaire des licences en CSV.

        Args:
            inventory: Liste (format get_inventory)
            filepath: Chemin du fichier de sortie

        Returns:
            True si succès
        """
        try:
            if not inventory:
                return False

            fieldnames = [
                "sku_id", "part_number", "display_name",
                "total", "consumed", "available", "warning",
            ]

            rows = []
            for item in inventory:
                row = dict(item)
                # Libellé lisible pour le CSV
                row["warning"] = "Oui" if row.get("warning") else "Non"
                rows.append(row)

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            return True
        except Exception as e:
            logger.error(f"Erreur export CSV licences : {e}")
            return False