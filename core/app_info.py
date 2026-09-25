"""
Informations applicatives partagées (version + dépôt GitHub).

Une seule source de vérité pour la version courante — le comparateur
de mises à jour (core/updater.py) s'appuie dessus.
"""

# Version courante de l'application (affichée et comparée aux tags GitHub)
APP_VERSION = "2.1.0"

# Dépôt GitHub des releases (public — pas d'authentification requise)
REPO_OWNER = "GregDepan"
REPO_NAME = "graph-tenant-manager"

# Nom du binaire distribué par les releases GitHub
EXE_NAME = "GraphTenantManager.exe"


def app_version_tuple() -> tuple:
    """Version courante en tuple d'entiers (2.1.0 → (2, 1, 0))."""
    return parse_version(APP_VERSION)


def parse_version(raw: str) -> tuple:
    """
    Extrait un tuple d'entiers d'un tag/numéro de version.

    'v2.1.0' → (2, 1, 0) ; '2.1' → (2, 1) ; 'vX' → ().
    Les segments non numériques sont ignorés (robuste aux tags exotiques).
    """
    parts = []
    for chunk in str(raw or "").strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts)