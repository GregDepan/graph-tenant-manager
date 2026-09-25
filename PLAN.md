# Plan de Développement : Gestionnaire Multi-Tenants Microsoft Graph

> ⚠️ **Document historique** (conception initiale, avant v1.0). L'état
> réel du projet est décrit dans `README.md` et `CHANGELOG.md` — ce plan
> est conservé comme référence d'architecture. Ne pas suivre tel quel.

## 📊 Synthèse des Fonctionnalités Microsoft Graph

### **Microsoft Graph PowerShell SDK**
- **Wrapper API complet** : Toutes les API Microsoft Graph exposées en cmdlets PowerShell
- **Versions** : v1.0 (stable) et beta (fonctionnalités preview)
- **Authentification** : MSAL (moderne), supporte delegated et app-only
- **Cross-platform** : Windows, macOS, Linux, PowerShell 7+
- **Modules** : `Microsoft.Graph` (v1.0) et `Microsoft.Graph.Beta` (beta)
- **Remplace** : Azure AD PowerShell et MSOnline

### **API Microsoft Graph REST**
- **Endpoint unique** : `https://graph.microsoft.com/{version}/{resource}`
- **Services couverts** :
  - ✅ Microsoft Entra ID (utilisateurs, groupes, appareils, rôles)
  - ✅ Exchange Online (mails, calendriers, contacts)
  - ✅ SharePoint & OneDrive (fichiers, sites)
  - ✅ Teams (équipes, canaux, conversations)
  - ✅ Intune (gestion appareils)
  - ✅ Sécurité & conformité

### **Gestion Multi-Tenants (Beta)**
- **Tenant Management APIs** :
  - Lister tenants : `GET /tenantRelationships/managedTenants/tenants`
  - Détails tenant : `GET /tenantRelationships/managedTenants/{tenantId}`
  - Configuration management (dérive configuration)
  - Cross-tenant access policies
  - Multitenant organizations
  - Backup & Restore (Entra + M365)
  - Cross-tenant migration (Exchange, Teams, SharePoint)

### **Permissions Requises**
- **Lecture** : `ManagedTenants.Read.All`, `Directory.Read.All`, `User.Read.All`
- **Écriture** : `ManagedTenants.ReadWrite.All`, `Directory.ReadWrite.All`
- **Auth** : Delegated (utilisateur connecté) ou Application (daemon)

---

## 🎯 Architecture du Programme Python

### **Stack Technique**
```
Python 3.10+
├── msgraph-sdk (SDK officiel Microsoft)
├── azure-identity (authentification MSAL)
├── tkinter + ttk (GUI native Python)
├── asyncio (requêtes asynchrones)
└── configparser (gestion config multi-tenants)
```

### **Pourquoi tkinter plutôt que PyQt ?**
- ✅ Inclus dans Python (aucune dépendance externe)
- ✅ Léger et rapide à démarrer
- ✅ Suffisant pour un dashboard d'administration
- ✅ Cross-platform natif
- ⚠️ Look moins moderne (compensé par ttk themes)

---

## 📁 Structure du Projet

```
graph-tenant-manager/
├── main.py                      # Point d'entrée + GUI principale
├── config.cfg                   # Configuration multi-tenants
├── requirements.txt             # Dépendances
│
├── core/
│   ├── __init__.py
│   ├── auth.py                  # Gestion authentification (MSAL)
│   ├── graph_client.py          # Wrapper SDK Microsoft Graph
│   └── tenant_store.py          # Store des tenants connectés
│
├── services/
│   ├── __init__.py
│   ├── tenant_service.py        # Ops: lister, switch, infos tenant
│   ├── users_service.py         # CRUD utilisateurs
│   ├── groups_service.py        # CRUD groupes
│   ├── devices_service.py       # Gestion appareils
│   ├── mail_service.py          # Exchange Online
│   └── reports_service.py       # Rapports & stats
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py           # Fenêtre principale
│   ├── tenant_selector.py       # Widget sélection tenant
│   ├── users_panel.py           # Panel gestion utilisateurs
│   ├── groups_panel.py          # Panel gestion groupes
│   ├── devices_panel.py         # Panel appareils
│   ├── mail_panel.py            # Panel Exchange
│   └── dashboard.py             # Vue d'ensemble
│
└── utils/
    ├── __init__.py
    ├── logger.py                # Logging centralisé
    └── validators.py            # Validation données
```

---

## 🔐 Module d'Authentification (`core/auth.py`)

### **Fonctionnalités**
```python
class TenantAuthManager:
    """
    Gère l'authentification multi-tenants avec MSAL
    """
    
    # 1. Authentification Interactive (première connexion)
    def connect_tenant(self, tenant_id: str, client_id: str) -> GraphServiceClient:
        """
        - Ouvre navigateur pour consentement
        - Récupère token d'accès
        - Initialise GraphServiceClient
        - Stocke credentials dans session
        """
    
    # 2. Authentification Silencieuse (tenants déjà autorisés)
    def silent_connect(self, tenant_id: str) -> GraphServiceClient:
        """
        - Utilise token refresh
        - Revalide automatiquement si expiré
        """
    
    # 3. Switch Tenant
    def switch_tenant(self, new_tenant_id: str) -> None:
        """
        - Déconnecte du tenant actuel
        - Connecte au nouveau tenant
        - Met à jour le client Graph
        """
    
    # 4. Déconnexion
    def disconnect(self, tenant_id: str = None) -> None:
        """
        - Révoque tokens
        - Nettoie cache
        """
    
    # 5. Gestion des Permissions
    def check_permissions(self, required_scopes: list) -> bool:
        """
        - Vérifie scopes consentis
        - Demande consentement additionnel si besoin
        """
```

### **Scopes par Défaut**
```ini
graphUserScopes = 
    Directory.Read.All
    Directory.ReadWrite.All
    User.Read.All
    User.ReadWrite.All
    Group.Read.All
    Group.ReadWrite.All
    Device.Read.All
    Device.ReadWrite.All
    Mail.Read
    Mail.Send
    Sites.Read.All
    ManagedTenants.Read.All
```

---

## 🖥️ Interface Graphique (`gui/`)

### **Fenêtre Principale**
```
┌─────────────────────────────────────────────────────────────┐
│  🏢 Graph Tenant Manager                      [_][□][X]    │
├─────────────────────────────────────────────────────────────┤
│  Tenant: [Contoso ▼]  👤 admin@contoso.com   🔄 Sync      │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  📊 DASHBOARD │  📈 Statistiques                           │
│  👥 UTILISATEURS│  • Utilisateurs: 145                     │
│  👥 GROUPES   │  • Groupes: 23                             │
│  📱 APPAREILS  │  • Appareils: 89                           │
│  📧 EXCHANGE  │  • Licences M365: 140                      │
│  ⚙️ CONFIG    │                                              │
│              │  🔔 Alertes                                │
│              │  • 3 utilisateurs sans licence              │
│              │  • 2 appareils non conformes                │
│              │                                              │
├──────────────┴──────────────────────────────────────────────┤
│  Status: ✓ Connecté | Last sync: 14:32                     │
└─────────────────────────────────────────────────────────────┘
```

### **Widgets Clés**

#### **1. Tenant Selector (`tenant_selector.py`)**
```python
class TenantSelector(ttk.Combobox):
    """
    - Dropdown avec liste des tenants connectés
    - Affiche: nom du tenant + domaine + status
    - Permet switch rapide
    - Indicateur visuel: ✓ connecté, ⚠️ token expiré
    """
```

#### **2. Dashboard (`dashboard.py`)**
```python
class Dashboard(ttk.Frame):
    """
    Widgets:
    - Cards statistiques (utilisateurs, groupes, appareils)
    - Graphique camembert (répartition licences)
    - Liste dernières alertes
    - Bouton refresh global
    """
```

#### **3. Panel Utilisateurs (`users_panel.py`)**
```python
class UsersPanel(ttk.Frame):
    """
    - Treeview liste utilisateurs (nom, email, licence, status)
    - Barre recherche/filtre (par nom, département, licence)
    - Boutons: ➕ Ajouter, ✏️ Modifier, 🗑️ Supprimer, 🔒 Reset MDP
    - Double-clic → Détails utilisateur
    - Export CSV/Excel
    """
    
    ops_supportees = [
        "Créer utilisateur",
        "Modifier profil",
        "Assigner licence",
        "Réinitialiser mot de passe",
        "Bloquer/débloquer",
        "Supprimer (soft delete)",
        "Exporter liste"
    ]
```

#### **4. Panel Groupes (`groups_panel.py`)**
```python
class GroupsPanel(ttk.Frame):
    """
    - Treeview hiérarchique (groupes + membres)
    - Filtre par type: Microsoft 365, Sécurité, Distribution
    - Boutons: ➕ Créer, 👥 Gérer membres, 📊 Stats
    - Support groupes dynamiques (règles membership)
    """
```

#### **5. Panel Appareils (`devices_panel.py`)**
```python
class DevicesPanel(ttk.Frame):
    """
    - Liste appareils (nom, type, OS, propriétaire, conformité)
    - Filtre: Windows, macOS, iOS, Android
    - Indicateurs: ✅ conforme, ⚠️ non conforme, ❌ bloqué
    - Actions: Wipe, Retire, Sync
    """
```

#### **6. Panel Exchange (`mail_panel.py`)**
```python
class MailPanel(ttk.Frame):
    """
    - Stats boîtes mail (taille, dernier login)
    - Gestion shared mailboxes
    - Création règles de transport
    - Export rapports de livraison
    """
```

---

## 🛠️ Services (`services/`)

### **Tenant Service**
```python
class TenantService:
    def __init__(self, graph_client: GraphServiceClient):
        self.client = graph_client
    
    async def list_tenants(self) -> list[Tenant]:
        """
        GET /tenantRelationships/managedTenants/tenants
        """
    
    async def get_tenant_info(self, tenant_id: str) -> Tenant:
        """
        GET /tenantRelationships/managedTenants/{tenantId}
        Retourne: displayName, defaultDomain, tenantId, status
        """
    
    async def check_configuration_drift(self) -> list[Drift]:
        """
        Détecte dérive configuration (Conditional Access, Security Defaults)
        """
```

### **Users Service**
```python
class UsersService:
    async def get_all_users(self, filters: dict = None) -> list[User]:
        """
        GET /users?$filter=...&$select=id,displayName,mail,assignedLicenses
        Supporte: pagination, tri, recherche
        """
    
    async def create_user(self, user_data: dict) -> User:
        """
        POST /users
        body: displayName, userPrincipalName, passwordProfile, assignedLicenses
        """
    
    async def update_user(self, user_id: str, updates: dict) -> User:
        """
        PATCH /users/{id}
        """
    
    async def delete_user(self, user_id: str, soft_delete: bool = True) -> None:
        """
        DELETE /users/{id} (soft delete par défaut)
        """
    
    async def reset_password(self, user_id: str, new_password: str) -> None:
        """
        POST /users/{id}/resetPassword
        """
    
    async def assign_license(self, user_id: str, sku_id: str) -> None:
        """
        PATCH /users/{id} avec assignedLicenses
        """
```

### **Groups Service**
```python
class GroupsService:
    async def get_all_groups(self, group_type: str = None) -> list[Group]:
        """
        GET /groups?$filter=groupTypes/any(...)
        Types: Microsoft365, Security, Distribution
        """
    
    async def create_group(self, group_data: dict) -> Group:
        """
        POST /groups
        body: displayName, mailEnabled, securityEnabled, groupTypes
        """
    
    async def add_member(self, group_id: str, user_id: str) -> None:
        """
        POST /groups/{id}/members/$ref
        """
    
    async def remove_member(self, group_id: str, user_id: str) -> None:
        """
        DELETE /groups/{id}/members/{userId}/$ref
        """
```

### **Reports Service**
```python
class ReportsService:
    async def get_user_report(self) -> dict:
        """
        GET /reports/getUserUsageDetail(period='D7')
        """
    
    async def get_device_report(self) -> dict:
        """
        GET /reports/getDeviceUsageDetail(period='D7')
        """
    
    async def get_license_report(self) -> dict:
        """
        GET /reports/getOffice365ActiveUserDetail(period='D7')
        """
    
    async def export_to_csv(self, report_type: str, path: str) -> str:
        """
        Génère fichier CSV exportable
        """
```

---

## 📄 Fichier de Configuration (`config.cfg`)

```ini
[azure]
# Application registration (à créer dans Entra ID)
clientId = VOTRE_CLIENT_ID
tenantId = common  # ou ID tenant spécifique pour single-tenant

# Scopes pour authentification delegated
graphUserScopes = 
    Directory.Read.All
    Directory.ReadWrite.All
    User.Read.All
    Group.Read.All
    Device.Read.All
    Mail.Read
    ManagedTenants.Read.All

[tenants]
# Liste des tenants clients
# Format: nom_affiche = tenant_id,domaine,notes
client1 = 12345678-1234-1234-1234-123456789abc,contoso.com,Client principal
client2 = 87654321-4321-4321-4321-cba987654321,fabrikam.com,Test environment
client3 = abcdef12-3456-7890-abcd-ef1234567890,adatum.com,Migration en cours

[ui]
# Préférences interface
theme = default  # default, alt, clam, victor
language = fr
refresh_interval = 300  # secondes

[logging]
level = INFO  # DEBUG, INFO, WARNING, ERROR
file = logs/graph_manager.log
max_size = 10MB
```

---

## 🚀 Plan de Développement (Phases)

### **Phase 1 : Socle (Semaine 1)**
- [ ] Setup projet + structure dossiers
- [ ] Module authentification (`core/auth.py`)
- [ ] Configuration multi-tenants (`config.cfg`)
- [ ] Tests connexion 1 tenant

### **Phase 2 : GUI de Base (Semaine 2)**
- [ ] Fenêtre principale avec tkinter
- [ ] Tenant selector (dropdown)
- [ ] Dashboard avec stats basiques
- [ ] Logging + gestion erreurs

### **Phase 3 : Services Utilisateurs (Semaine 3)**
- [ ] `UsersService` complet (CRUD)
- [ ] Panel utilisateurs GUI
- [ ] Recherche/filtres
- [ ] Export CSV

### **Phase 4 : Groupes & Appareils (Semaine 4)**
- [ ] `GroupsService` (CRUD + membres)
- [ ] `DevicesService` (liste + conformité)
- [ ] Panels GUI associés

### **Phase 5 : Exchange & Rapports (Semaine 5)**
- [ ] `MailService` (stats boîtes mail)
- [ ] `ReportsService` (rapports usage)
- [ ] Export Excel/PDF

### **Phase 6 : Polish (Semaine 6)**
- [ ] Thèmes UI (ttk styles)
- [ ] Raccourcis clavier
- [ ] Documentation utilisateur
- [ ] Packaging (.exe Windows, .app macOS)

---

## 🔒 Sécurité & Bonnes Pratiques

### **Gestion des Secrets**
- ❌ JAMAIS de mots de passe en dur dans `config.cfg`
- ✅ Utiliser **Azure Key Vault** ou **Windows Credential Manager**
- ✅ Tokens stockés en mémoire (session uniquement)
- ✅ Refresh tokens chiffrés si persistence nécessaire

### **Permissions Least Privilege**
```python
# Demander uniquement les scopes nécessaires
SCOPS_UTILISATEURS_SEULS = [
    "User.Read.All",
    "User.ReadWrite.All"
]

SCOPS_COMPLETS = [
    "Directory.Read.All",
    "Directory.ReadWrite.All",
    "User.Read.All",
    "Group.Read.All",
    # ...
]
```

### **Gestion des Erreurs**
```python
try:
    await graph_client.users.get()
except ODataError as e:
    logger.error(f"Graph API error: {e.error.message}")
    show_error_dialog("Erreur API", e.error.message)
except AuthenticationError as e:
    logger.error(f"Auth failed: {str(e)}")
    reconnect_tenant()
except Exception as e:
    logger.exception(f"Unexpected error: {str(e)}")
```

---

## 📦 Installation & Déploiement

### **requirements.txt**
```txt
msgraph-sdk>=1.0.0
azure-identity>=1.15.0
asyncio>=3.4.3
tkinter  # inclus dans Python
```

### **Installation**
```bash
# 1. Cloner le repo
git clone https://github.com/ton-repo/graph-tenant-manager.git
cd graph-tenant-manager

# 2. Créer venv
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 3. Installer dépendances
pip install -r requirements.txt

# 4. Configurer
cp config.cfg.example config.cfg
# Éditer config.cfg avec tes infos

# 5. Lancer
python main.py
```

### **Enregistrement Application (Entra ID)**
1. Aller sur https://entra.microsoft.com
2. **Applications** → **Inscriptions d'application** → **Nouvelle inscription**
3. Nom: `Graph Tenant Manager`
4. **Types de comptes pris en charge** : "Comptes dans n'importe quel annuaire organisationnel"
5. **URI de redirection** : Laisser vide (device code flow)
6. **Authentification** → **Paramètres avancés** → **Autoriser les flux de client public** : Oui
7. Copier **Client ID** et **Tenant ID** dans `config.cfg`

---

## 🎯 Fonctionnalités Futures (V2)

- [ ] **Mode daemon** : Exécution automatique (scripts planifiés)
- [ ] **Webhooks** : Notifications temps réel (changement utilisateurs)
- [ ] **Bulk operations** : Actions en masse (import CSV)
- [ ] **Audit logs** : Historique des actions
- [ ] **Rôles personnalisés** : RBAC interne à l'app
- [ ] **API REST** : Exposer l'app en API pour intégration
- [ ] **Version web** : Dashboard Flask/FastAPI + React

---

## 📚 Ressources & Documentation

- **Docs officielles** : https://learn.microsoft.com/graph/
- **Graph Explorer** : https://developer.microsoft.com/graph/graph-explorer (tester API)
- **SDK Python** : https://github.com/microsoftgraph/msgraph-sdk-python
- **Permissions** : https://learn.microsoft.com/graph/permissions-reference
- **PowerShell SDK** : https://learn.microsoft.com/powershell/microsoftgraph/overview

---

## ✅ Prochaines Actions Immédiates

1. **Créer l'application dans Entra ID** (5 min)
2. **Initialiser le repo GitHub** avec la structure ci-dessus
3. **Coder `core/auth.py`** (premier module critique)
4. **Tester connexion 1 tenant** avec le SDK Python
5. **Itérer sur la GUI** une fois l'authentification fonctionnelle

---

**Note** : Ce plan est conçu pour être **modulaire** et **évolutif**. Tu peux commencer avec un seul tenant et ajouter les autres progressivement. L'architecture permet d'ajouter de nouveaux services (ex: Teams, SharePoint) sans refondre le code existant.
