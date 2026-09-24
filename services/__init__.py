"""
Services package - Couche métier pour les opérations Microsoft Graph.

Chaque service encapsule un domaine (utilisateurs, groupes, appareils,
licences) et transforme les objets SDK bruts en dictionnaires stables
consommés par la GUI.
"""

from services.users_service import UsersService
from services.groups_service import GroupsService
from services.devices_service import DevicesService
from services.licenses_service import LicensesService

__all__ = ["UsersService", "GroupsService", "DevicesService", "LicensesService"]