"""
Service de gestion des utilisateurs Microsoft Graph.

Couche métier entre la GUI et le wrapper Graph (GraphClientWrapper).
Le wrapper expose des objets SDK bruts (User) ; ce service les transforme
en dictionnaires prêts à afficher et encapsule les opérations CRUD.

Note : l'import de GraphClientWrapper est réservé au typage (TYPE_CHECKING)
afin que ce module reste importable même si la couche core est en cours
d'évolution — aucun accès direct à core/ à l'exécution.
"""

import csv
import secrets
import string
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover
    from core.graph_client import GraphClientWrapper


# Alphabet autorisé pour les mots de passe temporaires (complexité Microsoft)
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"


def _generate_temp_password(length: int = 14) -> str:
    """
    Génère un mot de passe temporaire robuste.

    Garantit au moins une majuscule, une minuscule, un chiffre et un
    caractère spécial (politique de complexité Microsoft), puis mélange
    le tout de façon cryptographiquement sûre.
    """
    specials = "!@#$%^&*-_=+?"
    parts = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(specials),
    ]
    parts += [secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(max(length - 4, 0))]
    # Mélange pour éviter un motif prévisible en début de chaîne
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts)


def _format_user(user: Any) -> Dict[str, Any]:
    """
    Transforme un objet User du SDK Graph en dictionnaire exploitable
    par la GUI (clés stables, valeurs jamais None pour l'affichage).
    """
    # Licences assignées : liste d'objets avec sku_id (peut être absent
    # selon les champs demandés à l'API — accès défensif)
    assigned = getattr(user, "assigned_licenses", None) or []
    license_skus = [
        str(getattr(lic, "sku_id"))
        for lic in assigned
        if getattr(lic, "sku_id", None)
    ]

    business_phones = getattr(user, "business_phones", None) or []
    created = getattr(user, "created_date_time", None)

    return {
        "id": user.id,
        "display_name": user.display_name or "N/A",
        "email": user.mail or user.user_principal_name or "",
        "user_principal_name": user.user_principal_name or "",
        "job_title": user.job_title or "",
        "department": user.department or "",
        "office_location": user.office_location or "",
        "mobile_phone": user.mobile_phone or "",
        "business_phone": business_phones[0] if business_phones else "",
        "account_enabled": user.account_enabled,
        "created_date_time": str(created) if created else "",
        "has_license": bool(license_skus),
        "license_skus": license_skus,
    }


class UsersService:
    """
    Service métier pour la gestion des utilisateurs.

    Contrat d'interface (la GUI code contre cette API) :
        get_all_users_formatted() -> List[dict]
        search(term) -> List[dict]
        create(user_data) -> Optional[str]
        update(user_id, updates) -> bool
        delete(user_id) -> bool
        reset_password(user_id, new_password, force_change=True) -> bool
        set_blocked(user_id, blocked=True) -> bool
        assign_license(user_id, sku_id, remove=False) -> bool
        unassign_license(user_id, sku_id) -> bool
        export_to_csv(users, filepath) -> bool
    """

    def __init__(self, graph_wrapper: "GraphClientWrapper"):
        """
        Initialise le service.

        Args:
            graph_wrapper: Instance de GraphClientWrapper authentifié
        """
        self.graph = graph_wrapper

    # ==================== LECTURE ====================

    async def get_all_users_formatted(self) -> List[Dict[str, Any]]:
        """
        Récupère tous les utilisateurs du tenant, formatés pour la GUI.

        Returns:
            Liste de dictionnaires avec les clés : id, display_name, email,
            user_principal_name, job_title, department, office_location,
            mobile_phone, business_phone, account_enabled,
            created_date_time, has_license, license_skus
        """
        # limit=None côté wrapper => pagination complète du tenant
        users = await self.graph.get_all_users()
        return [_format_user(u) for u in users]

    async def search(self, term: str) -> List[Dict[str, Any]]:
        """
        Recherche des utilisateurs par terme (nom ou email).

        Args:
            term: Terme de recherche

        Returns:
            Liste de dictionnaires (mêmes clés que get_all_users_formatted)
        """
        if not term or not term.strip():
            # Terme vide : retourne l'inventaire complet
            return await self.get_all_users_formatted()

        users = await self.graph.search_users(term.strip())
        return [_format_user(u) for u in users]

    # ==================== ÉCRITURE ====================

    async def create(self, user_data: Dict[str, Any]) -> Optional[str]:
        """
        Crée un utilisateur.

        Args:
            user_data: Dictionnaire (clés camelCase) avec :
                - displayName (requis par Graph)
                - userPrincipalName (requis — sinon échec contrôlé)
                - mailNickname (optionnel, déduit de l'UPN si absent)
                - password (optionnel, mot de passe temporaire robuste généré)
                - forceChangePassword (optionnel, True par défaut)
                - department, jobTitle, officeLocation, mobilePhone (optionnels)

        Returns:
            ID de l'utilisateur créé, ou None en cas d'échec
        """
        upn = (user_data.get("userPrincipalName") or "").strip()
        if not upn:
            # userPrincipalName obligatoire : pas de tentative d'appel API
            logger.error("Création utilisateur impossible : userPrincipalName absent.")
            return None

        mail_nickname = user_data.get("mailNickname") or upn.split("@")[0]
        password = user_data.get("password") or _generate_temp_password()

        create_data: Dict[str, Any] = {
            "displayName": user_data.get("displayName"),
            "userPrincipalName": upn,
            "mailNickname": mail_nickname,
            "passwordProfile": {
                "password": password,
                "forceChangePasswordNextSignIn": user_data.get("forceChangePassword", True),
            },
            "accountEnabled": True,
        }

        # Champs optionnels (uniquement s'ils sont renseignés)
        for camel_key in ("department", "jobTitle", "officeLocation", "mobilePhone"):
            if user_data.get(camel_key):
                create_data[camel_key] = user_data[camel_key]

        user = await self.graph.create_user(create_data)
        if user is None:
            logger.error(f"Création utilisateur échouée côté Graph : {upn}")
            return None

        logger.info(f"Utilisateur créé : {upn} (id={user.id})")
        return user.id

    async def update(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Met à jour un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            updates: Champs à mettre à jour (clés snake_case, ex. display_name)

        Returns:
            True si succès
        """
        return await self.graph.update_user(user_id, updates)

    async def delete(self, user_id: str) -> bool:
        """
        Supprime un utilisateur (suppression réversible par défaut, côté Graph).

        Args:
            user_id: ID de l'utilisateur

        Returns:
            True si succès
        """
        return await self.graph.delete_user(user_id)

    async def reset_password(self, user_id: str, new_password: str,
                             force_change: bool = True) -> bool:
        """
        Réinitialise le mot de passe d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            new_password: Nouveau mot de passe
            force_change: Obliger le changement au prochain login (transmis
                au wrapper, qui applique forceChangePasswordNextSignIn)

        Returns:
            True si succès
        """
        return await self.graph.reset_user_password(
            user_id, new_password, force_change=force_change
        )

    async def set_blocked(self, user_id: str, blocked: bool = True) -> bool:
        """
        Bloque ou débloque la connexion d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            blocked: True pour bloquer le compte, False pour le réactiver

        Returns:
            True si succès
        """
        return await self.graph.update_user(
            user_id, {"account_enabled": not blocked}
        )

    # ==================== LICENCES ====================

    async def assign_license(self, user_id: str, sku_id: str,
                             remove: bool = False) -> bool:
        """
        Assigne (ou retire) une licence à un utilisateur.

        Utilise le point d'entrée dédié assign_licenses du wrapper
        (l'ancien PATCH générique assigned_licenses était cassé).

        Args:
            user_id: ID de l'utilisateur
            sku_id: ID du SKU de licence
            remove: True pour retirer la licence au lieu de l'assigner

        Returns:
            True si succès
        """
        if remove:
            return await self.graph.assign_licenses(user_id, [], [sku_id])
        return await self.graph.assign_licenses(user_id, [sku_id], [])

    async def unassign_license(self, user_id: str, sku_id: str) -> bool:
        """
        Retire une licence d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            sku_id: ID du SKU de licence à retirer

        Returns:
            True si succès
        """
        return await self.graph.assign_licenses(user_id, [], [sku_id])

    # ==================== EXPORT ====================

    def export_to_csv(self, users: List[Dict[str, Any]], filepath: str) -> bool:
        """
        Exporte la liste des utilisateurs en CSV (inclut has_license et
        license_skus, cette dernière jointe par des ';').

        Args:
            users: Liste des utilisateurs (format get_all_users_formatted)
            filepath: Chemin du fichier de sortie

        Returns:
            True si succès
        """
        try:
            if not users:
                return False

            fieldnames = [
                "id", "display_name", "email", "user_principal_name",
                "job_title", "department", "office_location",
                "mobile_phone", "business_phone", "account_enabled",
                "created_date_time", "has_license", "license_skus",
            ]

            rows = []
            for user in users:
                row = dict(user)
                skus = row.get("license_skus") or []
                if isinstance(skus, (list, tuple)):
                    row["license_skus"] = ";".join(str(s) for s in skus)
                rows.append(row)

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

            return True
        except Exception as e:
            logger.error(f"Erreur export CSV utilisateurs : {e}")
            return False