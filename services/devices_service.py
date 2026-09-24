"""
Service de gestion des appareils Microsoft Graph.

Couche métier entre la GUI et le wrapper Graph (GraphClientWrapper).

Correctif conformité : l'ancien code déduisait la conformité de
account_enabled (faux — un appareil activé peut être non conforme).
On utilise désormais device.is_compliant tel que rapporté par Graph.
"""

import csv
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


def _determine_os_type(operating_system: Optional[str]) -> str:
    """Déduit un type d'OS lisible depuis la chaîne operating_system."""
    os_name = (operating_system or "").lower()
    if "windows" in os_name:
        return "Windows"
    if "android" in os_name:
        return "Android"
    if "ios" in os_name or "ipados" in os_name or "iphone" in os_name or "ipad" in os_name:
        return "iOS"
    if "mac" in os_name:
        return "macOS"
    if "linux" in os_name:
        return "Linux"
    return "Unknown"


def _format_compliance(is_compliant: Optional[bool]) -> str:
    """
    Convertit le statut de conformité Graph en libellé français.

    Args:
        is_compliant: True/False rapporté par Graph, None si inconnu

    Returns:
        'Conforme', 'Non conforme' ou 'Inconnu'
    """
    if is_compliant is None:
        return "Inconnu"
    return "Conforme" if is_compliant else "Non conforme"


def _format_device(device: Any) -> Dict[str, Any]:
    """Transforme un objet Device du SDK Graph en dictionnaire pour la GUI."""
    last_sign_in = getattr(device, "approximate_last_sign_in_date_time", None)
    return {
        "id": device.id,
        "display_name": device.display_name or "N/A",
        "device_id": device.device_id or "",
        "operating_system": device.operating_system or "Unknown",
        "os_version": device.operating_system_version or "",
        "os_type": _determine_os_type(device.operating_system),
        "manufacturer": device.manufacturer or "",
        "model": device.model or "",
        "account_enabled": device.account_enabled,
        "is_compliant": device.is_compliant,
        "compliance_status": _format_compliance(device.is_compliant),
        "approximate_last_sign_in_date_time": str(last_sign_in) if last_sign_in else "",
    }


class DevicesService:
    """
    Service métier pour la gestion des appareils.

    Contrat d'interface (la GUI code contre cette API) :
        get_all_devices_formatted() -> List[dict]
        get_device_by_id(device_id) -> Optional[dict]
        export_to_csv(devices, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        """
        Initialise le service.

        Args:
            graph_wrapper: Instance de GraphClientWrapper authentifié
        """
        self.graph = graph_wrapper

    # ==================== LECTURE ====================

    async def get_all_devices_formatted(self) -> List[Dict[str, Any]]:
        """
        Récupère tous les appareils du tenant, formatés pour la GUI.

        Correctif conformité : le statut est dérivé de device.is_compliant
        (et non plus de account_enabled) :
            None  -> 'Inconnu'
            True  -> 'Conforme'
            False -> 'Non conforme'

        Returns:
            Liste de dictionnaires avec les clés : id, display_name, device_id,
            operating_system, os_version, os_type, manufacturer, model,
            account_enabled, is_compliant, compliance_status,
            approximate_last_sign_in_date_time
        """
        # limit=None côté wrapper => pagination complète du tenant
        devices = await self.graph.get_all_devices()
        return [_format_device(d) for d in devices]

    async def get_device_by_id(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère un appareil par son ID, formaté pour la GUI.

        Args:
            device_id: ID de l'appareil (ID Graph, pas le device_id physique)

        Returns:
            Dictionnaire au même format que get_all_devices_formatted,
            ou None si introuvable
        """
        device = await self.graph.get_device_by_id(device_id)
        if not device:
            return None
        return _format_device(device)

    # ==================== EXPORT ====================

    def export_to_csv(self, devices: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte les appareils en CSV (inclut is_compliant et
        compliance_status).

        Args:
            devices: Liste des appareils (format get_all_devices_formatted)
            filepath: Chemin du fichier de sortie

        Returns:
            True si succès
        """
        try:
            if not devices:
                return False

            fieldnames = [
                "id", "display_name", "device_id", "operating_system",
                "os_version", "os_type", "manufacturer", "model",
                "account_enabled", "is_compliant", "compliance_status",
                "approximate_last_sign_in_date_time",
            ]

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(devices)

            return True
        except Exception as e:
            logger.error(f"Erreur export CSV appareils : {e}")
            return False