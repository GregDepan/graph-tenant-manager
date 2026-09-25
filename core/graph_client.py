"""
Wrapper Microsoft Graph Client
Fournit des méthodes utilitaires pour les opérations courantes.

Réécriture v1.1 :
- Pagination COMPLÈTE (plus de plafond à 100 objets)
- assign_licenses via la vraie API POST /users/{id}/assignLicenses
- Comptages via $count=true + ConsistencyLevel: eventual (1 requête)
- get_subscribed_skus (inventaire licences)
"""

from typing import Optional, List, Dict, Any

from msgraph import GraphServiceClient
from msgraph.generated.models.user import User
from msgraph.generated.models.group import Group
from msgraph.generated.models.device import Device
from msgraph.generated.models.assigned_license import AssignedLicense
from msgraph.generated.users.item.assign_license.assign_license_post_request_body import (
    AssignLicensePostRequestBody,
)

# v2.1.4 : champs demandés explicitement à Graph pour /users — sans
# $select, l'API renvoie un jeu minimal SANS assignedLicenses,
# accountEnabled, department, jobTitle (licences/état vides en GUI).
USER_SELECT_FIELDS = (
    "id", "displayName", "mail", "userPrincipalName",
    "jobTitle", "department", "officeLocation",
    "mobilePhone", "businessPhones",
    "accountEnabled", "assignedLicenses", "createdDateTime",
)


class GraphClientWrapper:
    """
    Wrapper autour de GraphServiceClient pour simplifier les appels API.
    """

    def __init__(self, graph_client: GraphServiceClient):
        self.client = graph_client

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------

    @staticmethod
    def _page_result(result, limit: Optional[int]) -> List[Any]:
        """
        Extrait la liste d'un résultat Kiota + suit odata_next_link
        jusqu'à épuisement (ou limite atteinte).
        """
        items: List[Any] = list(result.value or [])
        while getattr(result, "odata_next_link", None) and (
            limit is None or len(items) < limit
        ):
            # with_url renvoie un request builder qui suit l'URL de page
            result = result.with_url(result.odata_next_link) if hasattr(
                result, "with_url"
            ) else None
            if result is None:
                break
            items.extend(result.value or [])
        if limit is not None and len(items) > limit:
            items = items[:limit]
        return items

    async def _count(self, request_builder, builder_cls) -> int:
        """
        Compte les objets via $count=true + ConsistencyLevel: eventual.
        Fallback : compte la pagination complète.
        """
        try:
            qp = builder_cls(
                count=True,
                select=["id"],
            )
            rc = request_builder.RequestBuilderGetRequestConfiguration(
                query_parameters=qp,
                headers={"ConsistencyLevel": "eventual"},
            )
            result = await request_builder.get(request_configuration=rc)
            count = getattr(result, "odata_count", None)
            if count is not None:
                return int(count)
        except Exception as e:
            print(f"[Graph] Comptage $count indisponible, fallback pagination: {e}")
        return -1  # code d'erreur interne pour fallback

    # ------------------------------------------------------------------
    # UTILISATEURS
    # ------------------------------------------------------------------

    async def get_current_user(self) -> Optional[User]:
        """Récupère l'utilisateur connecté"""
        try:
            return await self.client.me.get()
        except Exception as e:
            print(f"Erreur get_current_user: {e}")
            return None

    async def get_all_users(self, limit: Optional[int] = None) -> List[User]:
        """
        Récupère les utilisateurs du tenant, pagination complète.
        limit=None → tous les utilisateurs.

        v2.1.4 : $select explicite — sans lui, Graph ne renvoie PAS
        assignedLicenses, accountEnabled, department, jobTitle (jeu
        minimal par défaut) → licences et état affichés vides/faux.
        """
        try:
            from msgraph.generated.users.users_request_builder import (
                UsersRequestBuilder,
            )
            qp = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                select=list(USER_SELECT_FIELDS),
            )
            rc = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=qp,
            )
            result = await self.client.users.get(request_configuration=rc)
            return self._page_result(result, limit)
        except Exception as e:
            print(f"Erreur get_all_users: {e}")
            return []

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Récupère un utilisateur par son ID (ou son UPN).

        v2.1.4 : $select explicite (cf. get_all_users).
        """
        try:
            from msgraph.generated.users.item.user_item_request_builder import (
                UserItemRequestBuilder,
            )
            qp = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
                select=list(USER_SELECT_FIELDS),
            )
            rc = UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
                query_parameters=qp,
            )
            return await self.client.users.by_user_id(user_id).get(request_configuration=rc)
        except Exception as e:
            print(f"Erreur get_user_by_id: {e}")
            return None

    async def search_users(self, search_term: str, limit: Optional[int] = None) -> List[User]:
        """
        Recherche des utilisateurs côté serveur via $filter startswith.
        Fallback : filtre client sur la liste complète.

        v2.1.4 : $select explicite (cf. get_all_users) — la recherche
        doit renvoyer les mêmes champs que la liste complète.
        """
        if not search_term:
            return []
        term = search_term.replace("'", "''")
        try:
            from msgraph.generated.users.users_request_builder import (
                UsersRequestBuilder,
            )

            qp = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                select=list(USER_SELECT_FIELDS),
                filter=(
                    f"startswith(displayName,'{term}') "
                    f"or startswith(userPrincipalName,'{term}')"
                ),
            )
            rc = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=qp,
            )
            result = await self.client.users.get(request_configuration=rc)
            return self._page_result(result, limit)
        except Exception as e:
            print(f"[Graph] Recherche serveur indisponible, filtre local: {e}")
            all_users = await self.get_all_users(limit=limit)
            return [
                u
                for u in all_users
                if search_term.lower() in (u.display_name or "").lower()
                or search_term.lower() in (u.user_principal_name or "").lower()
            ]

    async def create_user(self, user_data: Dict[str, Any]) -> Optional[User]:
        """
        Crée un nouvel utilisateur.

        user_data (camelCase):
            displayName, userPrincipalName, mailNickname,
            passwordProfile {password, forceChangePasswordNextSignIn},
            department, jobTitle, officeLocation, mobilePhone
        """
        if not user_data.get("userPrincipalName"):
            print("[Graph] create_user: userPrincipalName manquant, abandon")
            return None

        try:
            from msgraph.generated.models.password_profile import PasswordProfile

            new_user = User()
            new_user.display_name = user_data.get("displayName")
            new_user.user_principal_name = user_data.get("userPrincipalName")
            new_user.mail_nickname = user_data.get(
                "mailNickname", user_data["userPrincipalName"].split("@")[0]
            )
            new_user.account_enabled = user_data.get("accountEnabled", True)

            pp_data = user_data.get("passwordProfile")
            if pp_data:
                pp = PasswordProfile()
                pp.password = pp_data.get("password")
                pp.force_change_password_next_sign_in = pp_data.get(
                    "forceChangePasswordNextSignIn", True
                )
                new_user.password_profile = pp

            for field, attr in (
                ("department", "department"),
                ("jobTitle", "job_title"),
                ("officeLocation", "office_location"),
                ("mobilePhone", "mobile_phone"),
            ):
                if user_data.get(field) is not None:
                    setattr(new_user, attr, user_data[field])

            return await self.client.users.post(new_user)
        except Exception as e:
            print(f"Erreur create_user: {e}")
            return None

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        Met à jour un utilisateur. updates en snake_case (attributs du SDK).
        """
        try:
            user = User()
            for key, value in updates.items():
                setattr(user, key, value)
            await self.client.users.by_user_id(user_id).patch(user)
            return True
        except Exception as e:
            print(f"Erreur update_user: {e}")
            return False

    async def delete_user(self, user_id: str) -> bool:
        """Supprime un utilisateur (soft delete : 30 jours récupérables)"""
        try:
            await self.client.users.by_user_id(user_id).delete()
            return True
        except Exception as e:
            print(f"Erreur delete_user: {e}")
            return False

    async def reset_user_password(
        self, user_id: str, new_password: str, force_change: bool = True
    ) -> bool:
        """Réinitialise le mot de passe d'un utilisateur (PATCH passwordProfile)"""
        try:
            from msgraph.generated.models.password_profile import PasswordProfile

            user = User()
            pp = PasswordProfile()
            pp.password = new_password
            pp.force_change_password_next_sign_in = force_change
            user.password_profile = pp

            await self.client.users.by_user_id(user_id).patch(user)
            return True
        except Exception as e:
            print(f"Erreur reset_user_password: {e}")
            return False

    async def assign_licenses(
        self, user_id: str, add_sku_ids: List[str], remove_sku_ids: Optional[List[str]] = None
    ) -> bool:
        """
        Assigne/retire des licences via POST /users/{id}/assignLicenses.
        """
        try:
            body = AssignLicensePostRequestBody()
            body.add_licenses = [
                AssignedLicense(sku_id=sku) for sku in (add_sku_ids or [])
            ]
            body.remove_licenses = list(remove_sku_ids or [])

            await self.client.users.by_user_id(user_id).assign_license.post(body)
            return True
        except Exception as e:
            print(f"Erreur assign_licenses: {e}")
            return False

    async def get_subscribed_skus(self) -> List[Any]:
        """Récupère l'inventaire des licences du tenant (subscribedSkus)"""
        try:
            result = await self.client.subscribed_skus.get()
            return self._page_result(result, None)
        except Exception as e:
            print(f"Erreur get_subscribed_skus: {e}")
            return []

    # ------------------------------------------------------------------
    # GROUPES
    # ------------------------------------------------------------------

    async def get_all_groups(self, limit: Optional[int] = None) -> List[Group]:
        """Récupère les groupes, pagination complète"""
        try:
            result = await self.client.groups.get()
            return self._page_result(result, limit)
        except Exception as on_error:
            print(f"Erreur get_all_groups: {on_error}")
            return []

    async def get_group_by_id(self, group_id: str) -> Optional[Group]:
        """Récupère un groupe par son ID"""
        try:
            return await self.client.groups.by_group_id(group_id).get()
        except Exception as e:
            print(f"Erreur get_group_by_id: {e}")
            return None

    async def get_group_members(self, group_id: str) -> List[Any]:
        """Récupère les membres d'un groupe, pagination complète"""
        try:
            result = await self.client.groups.by_group_id(group_id).members.get()
            return self._page_result(result, None)
        except Exception as e:
            print(f"Erreur get_group_members: {e}")
            return []

    async def create_group(self, group_data: Dict[str, Any]) -> Optional[Group]:
        """
        Crée un groupe. group_data (camelCase):
            displayName, mailEnabled, securityEnabled, groupTypes, mailNickname, description
        """
        try:
            new_group = Group()
            new_group.display_name = group_data.get("displayName")
            new_group.mail_enabled = group_data.get("mailEnabled", False)
            new_group.security_enabled = group_data.get("securityEnabled", True)
            new_group.group_types = group_data.get("groupTypes", [])
            new_group.mail_nickname = group_data.get("mailNickname")
            if group_data.get("description"):
                new_group.description = group_data.get("description")
            return await self.client.groups.post(new_group)
        except Exception as e:
            print(f"Erreur create_group: {e}")
            return None

    async def add_group_member(self, group_id: str, member_id: str) -> bool:
        """Ajoute un membre à un groupe (référence directoryObject)"""
        try:
            from msgraph.generated.models.reference_create import ReferenceCreate

            reference = ReferenceCreate()
            reference.odata_id = (
                f"https://graph.microsoft.com/v1.0/directoryObjects/{member_id}"
            )
            await self.client.groups.by_group_id(group_id).members.ref.post(reference)
            return True
        except Exception as e:
            print(f"Erreur add_group_member: {e}")
            return False

    async def remove_group_member(self, group_id: str, member_id: str) -> bool:
        """Retire un membre d'un groupe"""
        try:
            await self.client.groups.by_group_id(group_id).members.by_directory_object_id(
                member_id
            ).ref.delete()
            return True
        except Exception as e:
            print(f"Erreur remove_group_member: {e}")
            return False

    # ------------------------------------------------------------------
    # APPAREILS
    # ------------------------------------------------------------------

    async def get_all_devices(self, limit: Optional[int] = None) -> List[Device]:
        """Récupère les appareils, pagination complète"""
        try:
            result = await self.client.devices.get()
            return self._page_result(result, limit)
        except Exception as e:
            print(f"Erreur get_all_devices: {e}")
            return []

    async def get_device_by_id(self, device_id: str) -> Optional[Device]:
        """Récupère un appareil par son ID"""
        try:
            return await self.client.devices.by_device_id(device_id).get()
        except Exception as e:
            print(f"Erreur get_device_by_id: {e}")
            return None

    # ------------------------------------------------------------------
    # SHAREPOINT / ONEDRIVE / TEAMS / EXCHANGE (workloads v2.1)
    # ------------------------------------------------------------------

    async def get_all_sites(self, limit: Optional[int] = None) -> List[Any]:
        """
        Récupère les sites SharePoint du tenant via /sites/getAllSites,
        pagination complète.
        """
        try:
            result = await self.client.sites.get_all_sites.get()
            return self._page_result(result, limit)
        except Exception as e:
            print(f"Erreur get_all_sites: {e}")
            return []

    async def get_site_drives(self, site_id: str) -> List[Any]:
        """Récupère les bibliothèques documentaires d'un site."""
        try:
            result = await self.client.sites.by_site_id(site_id).drives.get()
            return self._page_result(result, None)
        except Exception as e:
            print(f"Erreur get_site_drives: {e}")
            return []

    async def get_user_drive(self, user_id: str) -> Optional[Any]:
        """
        Récupère le lecteur OneDrive d'un utilisateur (/users/{id}/drive).
        None si l'utilisateur n'a pas de lecteur provisionné.
        """
        try:
            return await self.client.users.by_user_id(user_id).drive.get()
        except Exception as e:
            print(f"Erreur get_user_drive: {e}")
            return None

    async def get_all_teams(self, limit: Optional[int] = None) -> List[Any]:
        """
        Récupère toutes les équipes du tenant.

        /teams ne liste que les équipes dont l'utilisateur connecté est
        membre — pour un inventaire MSP complet on filtre /groups sur
        resourceProvisioningOptions/any(x:x eq 'Team').
        """
        try:
            from msgraph.generated.groups.groups_request_builder import (
                GroupsRequestBuilder,
            )

            qp = GroupsRequestBuilder.GroupsRequestBuilderGetQueryParameters(
                filter="resourceProvisioningOptions/any(x:x eq 'Team')",
                select=["id", "displayName", "mail", "proxyAddresses",
                        "visibility", "createdDateTime", "description"],
            )
            rc = GroupsRequestBuilder.GroupsRequestBuilderGetRequestConfiguration(
                query_parameters=qp,
                headers={"ConsistencyLevel": "eventual"},
            )
            result = await self.client.groups.get(request_configuration=rc)
            return self._page_result(result, limit)
        except Exception as e:
            print(f"Erreur get_all_teams: {e}")
            return []

    async def get_team_channels(self, team_id: str) -> List[Any]:
        """Récupère les canaux d'une équipe."""
        try:
            result = await self.client.teams.by_team_id(team_id).channels.get()
            return self._page_result(result, None)
        except Exception as e:
            print(f"Erreur get_team_channels: {e}")
            return []

    async def get_team_member_count(self, team_id: str) -> int:
        """
        Compte les membres d'une équipe via
        /teams/{id}/members/$count (ConsistencyLevel eventual).
        """
        try:
            from msgraph.generated.teams.item.members.members_request_builder import (
                MembersRequestBuilder,
            )

            qp = MembersRequestBuilder.MembersRequestBuilderGetQueryParameters(
                count=True, select=["id"]
            )
            rc = MembersRequestBuilder.MembersRequestBuilderGetRequestConfiguration(
                query_parameters=qp,
                headers={"ConsistencyLevel": "eventual"},
            )
            result = await self.client.teams.by_team_id(team_id).members.get(
                request_configuration=rc
            )
            count = getattr(result, "odata_count", None)
            if count is not None:
                return int(count)
        except Exception as e:
            print(f"Erreur get_team_member_count: {e}")
        return -1

    async def get_mailbox_usage_report(self, period: str = "D30") -> bytes:
        """
        Rapport MailboxUsageDetail (CSV brut en bytes) de l'API Reports.
        """
        try:
            raw = await self.client.reports.get_mailbox_usage_detail_with_period(
                period
            ).get()
            return raw or b""
        except Exception as e:
            print(f"Erreur get_mailbox_usage_report: {e}")
            return b""

    # ------------------------------------------------------------------
    # TENANT INFO + COMPTAGES
    # ------------------------------------------------------------------

    async def get_tenant_info(self) -> Optional[Dict[str, Any]]:
        """Récupère les informations du tenant (organization)"""
        try:
            orgs = await self.client.organization.get()
            if orgs and orgs.value:
                org = orgs.value[0]
                return {
                    "id": org.id,
                    "display_name": org.display_name,
                    "verified_domains": [
                        getattr(d, "name", "") for d in (org.verified_domains or [])
                    ],
                    "initial_domain": getattr(
                        next(
                            (d for d in (org.verified_domains or []) if getattr(d, "is_initial", False)),
                            {},
                        ),
                        "name",
                        "",
                    ),
                }
            return None
        except Exception as e:
            print(f"Erreur get_tenant_info: {e}")
            return None

    async def get_tenant_users_count(self) -> int:
        """Compte les utilisateurs ($count + fallback pagination)"""
        try:
            from msgraph.generated.users.users_request_builder import (
                UsersRequestBuilder,
            )

            qp = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                count=True, select=["id"]
            )
            rc = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=qp, headers={"ConsistencyLevel": "eventual"}
            )
            result = await self.client.users.get(request_configuration=rc)
            if result and result.odata_count is not None:
                return int(result.odata_count)
        except Exception as e:
            print(f"[Graph] Fallback comptage users (pagination): {e}")
        users = await self.get_all_users()
        return len(users)

    async def get_tenant_groups_count(self) -> int:
        """Compte les groupes ($count + fallback pagination)"""
        try:
            from msgraph.generated.groups.groups_request_builder import (
                GroupsRequestBuilder,
            )

            qp = GroupsRequestBuilder.GroupsRequestBuilderGetQueryParameters(
                count=True, select=["id"]
            )
            rc = GroupsRequestBuilder.GroupsRequestBuilderGetRequestConfiguration(
                query_parameters=qp, headers={"ConsistencyLevel": "eventual"}
            )
            result = await self.client.groups.get(request_configuration=rc)
            if result and result.odata_count is not None:
                return int(result.odata_count)
        except Exception as e:
            print(f"[Graph] Fallback comptage groups (pagination): {e}")
        groups = await self.get_all_groups()
        return len(groups)

    async def get_tenant_devices_count(self) -> int:
        """Compte les appareils ($count + fallback pagination)"""
        try:
            from msgraph.generated.devices.devices_request_builder import (
                DevicesRequestBuilder,
            )

            qp = DevicesRequestBuilder.DevicesRequestBuilderGetQueryParameters(
                count=True, select=["id"]
            )
            rc = DevicesRequestBuilder.DevicesRequestBuilderGetRequestConfiguration(
                query_parameters=qp, headers={"ConsistencyLevel": "eventual"}
            )
            result = await self.client.devices.get(request_configuration=rc)
            if result and result.odata_count is not None:
                return int(result.odata_count)
        except Exception as e:
            print(f"[Graph] Fallback comptage devices (pagination): {e}")
        devices = await self.get_all_devices()
        return len(devices)