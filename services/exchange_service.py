"""
Service métier Exchange Online : utilisation des boîtes aux lettres.

Couvre :
    - rapport d'utilisation par boîte (taille, nb éléments, dernière activité)
      via l'API Reports de Graph (CSV délivré en octets)
    - agrégats du tenant (nb boîtes, stockage total consommé)
    - export CSV du détail

L'API Reports renvoie un CSV brut (bytes) — pas des objets Kiota. Le
parsing est fait ici, en durcissant la lecture des colonnes : Microsoft
réserve le droit de réordonner les colonnes d'un rapport, seule la
première (UPN) et la présence de l'en-tête sont garanties. On localise
donc chaque colonne par son intitulé EN à chaque exécution.
"""

import csv
import io
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("GraphTenantManager")

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


# Colonnes attendues du rapport MailboxUsageDetail (noms EN officiels).
# On cherche l'index par intitulé car l'ordre des colonnes peut varier.
_MAILBOX_COLUMNS = {
    "upn": ("User Principal Name",),
    "display_name": ("Display Name",),
    "deleted": ("Is Deleted",),
    "storage_used": ("Storage Used (Byte)",),
    "item_count": ("Item Count",),
    "last_activity": ("Last Activity Date",),
}


def _parse_mailbox_csv(raw: bytes) -> List[Dict[str, Any]]:
    """
    Parse le CSV brut du rapport MailboxUsageDetail.

    Args:
        raw: contenu CSV en bytes (peut contenir un BOM)

    Returns:
        Liste de dicts normalisés (une entrée par boîte non supprimée)
    """
    if not raw:
        return []
    try:
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception:  # pragma: no cover
        return []

    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return []

    header = rows[0]
    idx: Dict[str, int] = {}
    for key, aliases in _MAILBOX_COLUMNS.items():
        for i, col in enumerate(header):
            if col.strip() in aliases:
                idx[key] = i
                break

    result: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue

        def at(key: str) -> str:
            i = idx.get(key)
            return row[i].strip() if i is not None and i < len(row) else ""

        if at("deleted").lower() in ("true", "yes", "1"):
            continue  # boîte supprimée : hors inventaire

        storage = at("storage_used")
        try:
            storage_bytes = int(float(storage)) if storage else 0
        except ValueError:
            storage_bytes = 0

        try:
            items = int(at("item_count")) if at("item_count") else 0
        except ValueError:
            items = 0

        result.append({
            "upn": at("upn"),
            "display_name": at("display_name"),
            "storage_used": storage_bytes,
            "item_count": items,
            "last_activity": at("last_activity"),
        })

    result.sort(key=lambda m: (m["display_name"] or m["upn"] or "").lower())
    return result


def _gb(value: Optional[int]) -> str:
    """Formate des octets en Go avec 1 décimale ('' si vide)."""
    if value is None:
        return ""
    try:
        return f"{int(value) / (1024 ** 3):.1f} Go"
    except (TypeError, ValueError):
        return ""


class ExchangeService:
    """
    Service métier pour l'utilisation Exchange du tenant.

    Contrat d'interface (la GUI code contre cette API) :
        get_mailbox_usage() -> List[dict]
        export_to_csv(mailboxes, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        self.graph = graph_wrapper

    # ------------------------------------------------------------------
    # Utilisation des boîtes
    # ------------------------------------------------------------------

    async def get_mailbox_usage(self, period: str = "D30") -> List[Dict[str, Any]]:
        """
        Rapport d'utilisation des boîtes du tenant.

        Args:
            period: fenêtre du rapport (D7, D30, D90 — défaut D30)

        Returns:
            Liste triée par nom, dicts avec clés : upn, display_name,
            storage_used (octets), item_count, last_activity
        """
        raw = await self.graph.get_mailbox_usage_report(period)
        mailboxes = _parse_mailbox_csv(raw)

        logger.info("Exchange : %d boîte(s) en activité", len(mailboxes))
        return mailboxes

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------

    def export_to_csv(self, mailboxes: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte le rapport boîtes en CSV (point-virgule, Excel FR).

        Args:
            mailboxes: liste de dicts issue de get_mailbox_usage()
            filepath: chemin du fichier de destination

        Returns:
            True si écrit, False sinon
        """
        if not mailboxes:
            logger.warning("Export CSV Exchange : aucune donnée")
            return False
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["Boîte", "UPN", "Taille", "Nb éléments",
                                 "Dernière activité"])
                for m in mailboxes:
                    writer.writerow([
                        m.get("display_name", ""),
                        m.get("upn", ""),
                        _gb(m.get("storage_used")),
                        m.get("item_count", ""),
                        m.get("last_activity", ""),
                    ])
            logger.info("Export Exchange CSV écrit : %s", filepath)
            return True
        except OSError as exc:
            logger.error("Export CSV Exchange impossible : %s", exc)
            return False