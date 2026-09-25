"""
Module d'authentification Microsoft Graph — v2.0 clé en main.

ZÉRO CONFIGURATION :
- Utilise l'application publique « Microsoft Graph PowerShell » de Microsoft
  (client ID well-known, pré-enregistrée multi-tenant par Microsoft).
  → AUCUNE application à créer dans Entra ID, ni chez toi ni chez le client.
- Le tenant est DÉDUIT AUTOMATIQUEMENT du compte qui se connecte
  (plus de GUID à saisir).
- Reconnexion silencieuse : AuthenticationRecord + cache de tokens persistés
  par tenant (~/.graph-tenant-manager/ ou %LOCALAPPDATA%/GraphTenantManager).

Flows supportés :
1. Navigateur (primaire) — s'ouvre automatiquement
2. Device code (fallback) — code à saisir sur microsoft.com/devicelogin
   (utile en RDP / serveur sans navigateur)

Le seul geste requis (imposé par Microsoft pour toute application) :
à la toute première connexion, l'admin coche « Consenter au nom de votre
organisation ». Une seule fois par client.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from azure.identity import (
    DeviceCodeCredential,
    InteractiveBrowserCredential,
    TokenCachePersistenceOptions,
    AuthenticationRecord,
)
from msgraph import GraphServiceClient

# Application publique multi-tenant de Microsoft « Microsoft Graph PowerShell ».
# Pré-enregistrée par Microsoft, utilisable par tout le monde (c'est celle que
# le module PowerShell officiel utilise quand on ne fournit pas de ClientId).
WELL_KNOWN_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

# Tenant « organizations » = n'importe quel compte scolaire/pro
DEFAULT_TENANT = "organizations"

# Scopes demandés (delegated). Doivent être consentis par un admin à la 1re
# connexion si le tenant l'exige (c'est le cas pour Directory.ReadWrite.All).
DEFAULT_SCOPES = (
    "User.Read.All User.ReadWrite.All Directory.Read.All Directory.ReadWrite.All "
    "Group.Read.All Group.ReadWrite.All GroupMember.Read.All "
    "Device.Read.All DeviceManagementManagedDevices.Read.All "
    "Organization.Read.All AuditLog.Read.All "
    # Workloads v2.1 : SharePoint, OneDrive, Exchange (Reports), Teams
    "Sites.Read.All Files.Read.All Reports.Read.All "
    "Team.ReadBasic.All Channel.ReadBasic.All TeamMember.Read.All"
)


def cache_dir() -> Path:
    """Dossier de cache cross-platform."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    else:
        base = str(Path.home())
    d = Path(base) / "GraphTenantManager" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TenantAuthManager:
    """
    Gestionnaire d'authentification multi-tenants, clé en main.

    Utilisation typique :
        auth = TenantAuthManager({})          # aucune config nécessaire
        client = auth.connect_interactive()   # navigateur → tenant déduit
        # ou :
        client = auth.connect_device_code(lambda code, url: print(code, url))
    """

    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        # Client ID : celui de Microsoft par défaut, surchargeable via config
        self.client_id = config.get("clientId") or WELL_KNOWN_CLIENT_ID
        self.custom_app = bool(config.get("clientId"))
        raw_scopes = config.get("graphUserScopes") or DEFAULT_SCOPES
        self.scopes: List[str] = list(str(raw_scopes).split())

        self._graph_clients: Dict[str, GraphServiceClient] = {}
        self._credentials: Dict[str, Any] = {}

        self._current_tenant_id: Optional[str] = None
        # Infos d'affichage par tenant : {tid: {name, username}}
        self._accounts: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Persistance (AuthenticationRecord par tenant)
    # ------------------------------------------------------------------

    def _record_path(self, tenant_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id)
        return cache_dir() / f"auth_record_{safe}.json"

    def _save_record(self, tenant_id: str, record: AuthenticationRecord,
                     username: str = "", tenant_name: str = "") -> None:
        try:
            payload = {
                "record": record.serialize(),
                "username": username,
                "tenant_name": tenant_name,
            }
            self._record_path(tenant_id).write_text(
                json.dumps(payload), encoding="utf-8"
            )
        except Exception as e:
            print(f"[Auth] Impossible de persister le record: {e}")

    def _load_record_payload(self, tenant_id: str) -> Optional[Dict]:
        try:
            path = self._record_path(tenant_id)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "record" in data:
                    return data
        except Exception as e:
            print(f"[Auth] Record illisible pour {tenant_id}: {e}")
        return None

    def forget_tenant(self, tenant_id: str) -> None:
        """Supprime tout (mémoire + disque) pour un tenant."""
        self._graph_clients.pop(tenant_id, None)
        self._credentials.pop(tenant_id, None)
        self._accounts.pop(tenant_id, None)
        if self._current_tenant_id == tenant_id:
            self._current_tenant_id = None
        try:
            self._record_path(tenant_id).unlink(missing_ok=True)
        except Exception:
            pass
        print(f"🗑️ Tenant {tenant_id} oublié (auth supprimée du disque)")

    def list_saved_tenants(self) -> List[Dict[str, str]]:
        """
        Tenants déjà autorisés sur ce poste (records persistés),
        ex : [{'tenant_id': '...', 'username': '...', 'tenant_name': '...'}]
        """
        saved = []
        try:
            for path in cache_dir().glob("auth_record_*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if "record" not in data:
                        continue
                    record = AuthenticationRecord.deserialize(data["record"])
                    saved.append({
                        "tenant_id": record.tenant_id,
                        "username": data.get("username") or record.username or "",
                        "tenant_name": data.get("tenant_name") or "",
                    })
                except Exception:
                    continue
        except Exception:
            pass
        return saved

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_options() -> TokenCachePersistenceOptions:
        # Chiffré par DPAPI (Windows) si possible, sinon refusé → mémoire
        return TokenCachePersistenceOptions(allow_unencrypted_cache=False)

    def _browser_credential(self, tenant_hint: str = "",
                            record: Optional[AuthenticationRecord] = None):
        """Credential navigateur (flow authorization code + PKCE)."""
        kwargs: Dict[str, Any] = {
            "client_id": self.client_id,
            "cache_persistence_options": self._cache_options(),
        }
        if not self.custom_app:
            # L'app well-known MS Graph PowerShell accepte http://localhost:PORT
            kwargs["redirect_uri"] = "http://localhost:8400"
        tid = tenant_hint or DEFAULT_TENANT
        if tid and tid not in ("auto", DEFAULT_TENANT):
            kwargs["tenant_id"] = tid
        if record is not None:
            kwargs["authentication_record"] = record
        return InteractiveBrowserCredential(**kwargs)

    def _device_credential(self, tenant_hint: str = "",
                           prompt_callback: Optional[Callable] = None):
        """Credential device code (aucune URI de redirection requise)."""
        kwargs: Dict[str, Any] = {
            "client_id": self.client_id,
            "cache_persistence_options": self._cache_options(),
        }
        tid = tenant_hint or DEFAULT_TENANT
        if tid and tid not in ("auto", DEFAULT_TENANT):
            kwargs["tenant_id"] = tid
        if prompt_callback is None:
            def prompt_callback(user_code: str, verification_uri: str, expires_on) -> None:
                print(f"\n🔐 Code de connexion : {user_code}")
                print(f"   À saisir sur      : {verification_uri}\n")
        kwargs["prompt_callback"] = prompt_callback
        return DeviceCodeCredential(**kwargs)

    # ------------------------------------------------------------------
    # Connexion (toutes SYNCHRONES — à appeler depuis un thread de travail)
    # ------------------------------------------------------------------

    def _register(self, credential, record: AuthenticationRecord,
                  tenant_name: str = "") -> GraphServiceClient:
        """Enregistre un tenant fraîchement authentifié."""
        tenant_id = record.tenant_id
        username = record.username or ""
        graph_client = GraphServiceClient(credentials=credential, scopes=self.scopes)

        self._credentials[tenant_id] = credential
        self._graph_clients[tenant_id] = graph_client
        self._accounts[tenant_id] = {
            "username": username,
            "tenant_name": tenant_name,
        }
        self._current_tenant_id = tenant_id

        self._save_record(tenant_id, record, username, tenant_name)
        return graph_client

    def connect_interactive(self, tenant_hint: str = "",
                            prompt_callback: Optional[Callable] = None) -> GraphServiceClient:
        """
        Connexion navigateur. Si le navigateur échoue (RDP, redirection non
        enregistrée, etc.) → bascule AUTOMATIQUEMENT en device code.

        tenant_hint : optionnel — domaine ou GUID client pour pré-filtrer les
        comptes. Vide = tous les comptes organisationnels.
        """
        credential = self._browser_credential(tenant_hint)
        try:
            record = credential.authenticate(scopes=self.scopes)
            print(f"✓ Connecté : {record.username} (tenant {record.tenant_id})")
            return self._register(credential, record)
        except Exception as e:
            print(f"[Auth] Navigateur indisponible ({e}) → bascule device code")
            return self.connect_device_code(tenant_hint, prompt_callback)

    def connect_device_code(self, tenant_hint: str = "",
                            prompt_callback: Optional[Callable] = None) -> GraphServiceClient:
        """
        Connexion device code : l'utilisateur ouvre microsoft.com/devicelogin
        et saisit le code affiché. Marche partout (RDP, serveurs).
        prompt_callback(device_code_prompt) reçoit l'objet avec .message
        (le prompt_callback de azure-identity est appelé AVANT l'auth).
        """
        credential = self._device_credential(tenant_hint, prompt_callback)
        # authenticate() existe aussi sur DeviceCodeCredential et déclenche
        # le prompt_callback avant de retourner le record.
        record = credential.authenticate(scopes=self.scopes)
        print(f"✓ Connecté : {record.username} (tenant {record.tenant_id})")
        return self._register(credential, record)

    def reconnect_silent(self, tenant_id: str) -> Optional[GraphServiceClient]:
        """
        Reconnexion silencieuse depuis le cache de tokens.
        Retourne le client Graph, ou None si le cache est expiré/absent.
        """
        if tenant_id in self._graph_clients:
            self._current_tenant_id = tenant_id
            return self._graph_clients[tenant_id]

        payload = self._load_record_payload(tenant_id)
        if payload is None:
            return None
        try:
            record = AuthenticationRecord.deserialize(payload["record"])
        except Exception:
            return None

        credential = self._browser_credential(record=record)
        try:
            credential.get_token(*self.scopes)  # cache → pas de navigateur
        except Exception as e:
            print(f"[Auth] Reconnexion silencieuse impossible pour {tenant_id}: {e}")
            return None

        graph_client = GraphServiceClient(credentials=credential, scopes=self.scopes)
        self._credentials[tenant_id] = credential
        self._graph_clients[tenant_id] = graph_client
        self._accounts[tenant_id] = {
            "username": payload.get("username", ""),
            "tenant_name": payload.get("tenant_name", ""),
        }
        self._current_tenant_id = tenant_id
        print(f"✓ Reconnexion silencieuse à {tenant_id}")
        return graph_client

    # ------------------------------------------------------------------
    # API de session
    # ------------------------------------------------------------------

    def get_client(self, tenant_id: Optional[str] = None) -> Optional[GraphServiceClient]:
        tid = tenant_id or self._current_tenant_id
        return self._graph_clients.get(tid) if tid else None

    def get_current_tenant(self) -> Optional[str]:
        return self._current_tenant_id

    def account_info(self, tenant_id: str) -> Dict[str, str]:
        """username + tenant_name connus pour un tenant."""
        return self._accounts.get(tenant_id, {"username": "", "tenant_name": ""})

    def list_connected_tenants(self) -> List[str]:
        return list(self._graph_clients.keys())

    def set_current_tenant(self, tenant_id: str) -> bool:
        """Bascule le tenant courant (déjà connecté)."""
        if tenant_id in self._graph_clients:
            self._current_tenant_id = tenant_id
            return True
        return False

    def disconnect(self, tenant_id: Optional[str] = None) -> None:
        """Déconnecte (mémoire seulement — le record reste pour reconnexion)."""
        if tenant_id:
            self._graph_clients.pop(tenant_id, None)
            self._credentials.pop(tenant_id, None)
            if self._current_tenant_id == tenant_id:
                self._current_tenant_id = None
            print(f"✓ Tenant {tenant_id} déconnecté (auth conservée)")
        else:
            self._graph_clients.clear()
            self._credentials.clear()
            self._current_tenant_id = None
            print("✓ Tous les tenants déconnectés")

    def is_connected(self, tenant_id: Optional[str] = None) -> bool:
        tid = tenant_id or self._current_tenant_id
        return tid in self._graph_clients if tid else False