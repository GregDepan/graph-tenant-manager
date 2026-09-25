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

# Scopes cœur (v2.0) — déjà consentis par tous les tenants connectés
# avant la v2.1 : ces permissions ne réclament jamais de nouveau
# consentement admin.
CORE_SCOPES = (
    "User.Read.All User.ReadWrite.All Directory.Read.All Directory.ReadWrite.All "
    "Group.Read.All Group.ReadWrite.All GroupMember.Read.All "
    "Device.Read.All DeviceManagementManagedDevices.Read.All "
    "Organization.Read.All AuditLog.Read.All"
)

# Scopes workloads (v2.1) — SharePoint, OneDrive, Exchange, Teams.
# ATTENTION : ces permissions exigent un NOUVEAU consentement admin par
# tenant. Si le tenant ne l'accorde pas (AADSTS65001), la connexion ne
# doit PAS échouer : on bascule en « permissions réduites » (scopes
# cœur uniquement, onglets workloads indisponibles).
WORKLOAD_SCOPES = (
    "Sites.Read.All Files.Read.All Reports.Read.All "
    "Team.ReadBasic.All Channel.ReadBasic.All TeamMember.Read.All"
)

DEFAULT_SCOPES = CORE_SCOPES + " " + WORKLOAD_SCOPES


def _scopes_list(scopes: str) -> List[str]:
    """Scopes espace-separated -> List[str] (typage explicite)."""
    return [str(part) for part in scopes.split()]


# Listes prêtes à l'emploi
CORE_SCOPES_LIST: List[str] = _scopes_list(CORE_SCOPES)
WORKLOAD_SCOPES_LIST: List[str] = _scopes_list(WORKLOAD_SCOPES)
DEFAULT_SCOPES_LIST: List[str] = _scopes_list(DEFAULT_SCOPES)

# Signatures d'erreur AAD indiquant un refus/besoin de consentement
_CONSENT_ERROR_KEYS = ("65001", "90094", "consent", "admin approval", "administrator has not consented")


def _is_consent_error(e: BaseException) -> bool:
    """True si l'exception correspond à un refus de consentement AAD."""
    msg = str(e).lower()
    return any(k in msg for k in _CONSENT_ERROR_KEYS)


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
        # Scopes réellement accordés par tenant : {tid: [scopes]}
        # (peut différer de self.scopes en « permissions réduites »)
        self._scopes_by_tenant: Dict[str, List[str]] = {}

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
                  tenant_name: str = "", scopes_used: Optional[List[str]] = None) -> GraphServiceClient:
        """Enregistre un tenant fraîchement authentifié."""
        tenant_id = record.tenant_id
        username = record.username or ""
        scopes = scopes_used if scopes_used is not None else self.scopes
        graph_client = GraphServiceClient(credentials=credential, scopes=scopes)

        self._credentials[tenant_id] = credential
        self._graph_clients[tenant_id] = graph_client
        self._accounts[tenant_id] = {
            "username": username,
            "tenant_name": tenant_name,
        }
        self._scopes_by_tenant[tenant_id] = scopes
        self._current_tenant_id = tenant_id

        self._save_record(tenant_id, record, username, tenant_name)
        return graph_client

    def tenant_scopes(self, tenant_id: str) -> List[str]:
        """Scopes réellement accordés pour un tenant (None → défaut complets)."""
        return self._scopes_by_tenant.get(tenant_id, self.scopes)

    def has_workload_scopes(self, tenant_id: Optional[str] = None) -> bool:
        """
        True si le tenant dispose des scopes workloads (SharePoint,
        OneDrive, Exchange, Teams). Faux en « permissions réduites ».
        """
        tid = tenant_id or self._current_tenant_id
        if not tid:
            return True  # pas encore connecté : on ne sait pas
        granted = self._scopes_by_tenant.get(tid)
        return not granted or all(s in granted for s in WORKLOAD_SCOPES_LIST)

    def connect_interactive(self, tenant_hint: str = "",
                            prompt_callback: Optional[Callable] = None) -> GraphServiceClient:
        """
        Connexion navigateur. Si le navigateur échoue (RDP, redirection non
        enregistrée, etc.) → bascule AUTOMATIQUEMENT en device code.

        Consentement : on demande d'abord les scopes complets (cœur +
        workloads). Si le tenant refuse le consentement admin requis par
        les scopes workloads (AADSTS65001), on RETOMBE sur les scopes
        cœur (déjà consentis depuis la v2.0) : la connexion réussit en
        « permissions réduites » plutôt que d'échouer totalement.
        """
        try:
            credential = self._browser_credential(tenant_hint)
            record = credential.authenticate(scopes=self.scopes)
            print(f"✓ Connecté : {record.username} (tenant {record.tenant_id})")
            return self._register(credential, record)
        except Exception as e:
            # Repli UN SEUL fois : uniquement si la tentative incluait les
            # scopes workloads (sinon le tenant refuse même les scopes cœur
            # → on laisse l'erreur remonter, pas de boucle infinie).
            if _is_consent_error(e) and any(s in self.scopes for s in WORKLOAD_SCOPES_LIST):
                print(f"[Auth] Consentement workloads refusé ({str(e)[:80]}) "
                      f"→ permissions réduites (scopes cœur)")
                return self._connect_reduced(tenant_hint, prompt_callback, self.connect_interactive)
            print(f"[Auth] Navigateur indisponible ({e}) → bascule device code")
            return self.connect_device_code(tenant_hint, prompt_callback)

    def _connect_reduced(self, tenant_hint: str, prompt_callback: Optional[Callable],
                         retry_method: Callable) -> GraphServiceClient:
        """Nouvelle tentative en permissions réduites (scopes cœur v2.0)."""
        self.scopes = list(CORE_SCOPES_LIST)
        try:
            return retry_method(tenant_hint, prompt_callback)
        finally:
            self.scopes = list(DEFAULT_SCOPES_LIST)

    def connect_device_code(self, tenant_hint: str = "",
                            prompt_callback: Optional[Callable] = None) -> GraphServiceClient:
        """
        Connexion device code : l'utilisateur ouvre microsoft.com/devicelogin
        et saisit le code affiché. Marche partout (RDP, serveurs).
        prompt_callback(user_code, verification_uri, expires_on) est
        appelé par azure-identity AVANT l'auth.
        """
        scopes = self.scopes
        credential = self._device_credential(tenant_hint, prompt_callback)
        # authenticate() existe aussi sur DeviceCodeCredential et déclenche
        # le prompt_callback avant de retourner le record.
        try:
            record = credential.authenticate(scopes=scopes)
        except Exception as e:
            if _is_consent_error(e) and any(s in scopes for s in WORKLOAD_SCOPES_LIST):
                print(f"[Auth] Consentement workloads refusé en device code "
                      f"({str(e)[:80]}) → réessayez après consentement admin, "
                      f"ou utilisez la connexion navigateur (repli auto).")
            raise
        print(f"✓ Connecté : {record.username} (tenant {record.tenant_id})")
        return self._register(credential, record, scopes_used=scopes)

    def reconnect_silent(self, tenant_id: str) -> Optional[GraphServiceClient]:
        """
        Reconnexion silencieuse depuis le cache de tokens.
        Retourne le client Graph, ou None si le cache est expiré/absent.

        v2.1.3 : les caches créés en v2.0 (11 scopes cœur) ne contiennent
        pas les tokens des scopes workloads — demander les 17 scopes
        échouait et cassait la reconnexion. On demande maintenant les
        scopes du tenant, puis on se replie sur les scopes cœur si le
        cache ne couvre que la v2.0.
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

        # Scopes à demander : ceux du tenant s'ils sont connus, sinon le
        # jeu complet. Si seul le jeu cœur marche (cache v2.0), le tenant
        # passe en permissions réduites — la reconnexion ne doit jamais
        # échouer pour cette raison.
        wanted = self._scopes_by_tenant.get(tenant_id, self.scopes)
        credential = self._browser_credential(record=record)
        scopes_ok = False
        try:
            credential.get_token(*wanted)  # cache → pas de navigateur
            scopes_ok = True
        except Exception as e:
            print(f"[Auth] Reconnexion avec scopes complets impossible : {str(e)[:80]}")
        if not scopes_ok:
            try:
                credential.get_token(*CORE_SCOPES_LIST)  # cache v2.0
            except Exception as e:
                print(f"[Auth] Reconnexion silencieuse impossible pour {tenant_id}: {e}")
                return None
            wanted = list(CORE_SCOPES_LIST)

        graph_client = GraphServiceClient(credentials=credential, scopes=wanted)
        self._credentials[tenant_id] = credential
        self._graph_clients[tenant_id] = graph_client
        self._accounts[tenant_id] = {
            "username": payload.get("username", ""),
            "tenant_name": payload.get("tenant_name", ""),
        }
        self._scopes_by_tenant[tenant_id] = wanted
        self._current_tenant_id = tenant_id
        print(f"✓ Reconnexion silencieuse à {tenant_id} "
              f"({'complète' if scopes_ok else 'permissions réduites'})")
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