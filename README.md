# 🏢 Graph Tenant Manager

Outil **clé en main** de gestion multi-tenants Microsoft 365 pour MSP/administrateurs.
Un .exe, un bouton « Connecter », le compte admin du client — c'est tout.

**v2.1.4** — voir `CHANGELOG.md`.

---

## 🚀 Ultra-simple (v2.0)

1. **Télécharge `GraphTenantManager.exe`** (release GitHub → https://github.com/GregDepan/graph-tenant-manager/releases)
2. Double-clic (SmartScreen : *Informations complémentaires → Exécuter quand même*)
3. Bouton **🔐 Connecter** → compte admin du client → cocher le consentement la 1re fois
4. Le tenant est déduit automatiquement — le dashboard s'affiche

**Aucune app à créer dans Entra ID.** L'outil utilise l'application publique
multi-tenant de Microsoft (« Microsoft Graph PowerShell ») — la même que le
module PowerShell officiel. **Aucune installation**, aucun Python requis.

> 📄 `CLIENT.md` = guide client en 1 page, prêt à envoyer avec l'exe.

## ✅ Fonctionnalités

| Onglet | Fonctionnalités |
|---|---|
| 📊 **Dashboard** | Compteurs, carte licences, alertes stock, infos tenant |
| 👥 **Utilisateurs** | Recherche, créer, modifier, réinit. MDP, licences, bloquer, supprimer, export CSV |
| 👥 **Groupes** | Filtre type, créer, gérer membres, supprimer, export CSV |
| 📱 **Appareils** | Filtre OS, conformité colorée, export CSV |
| 🔑 **Licences** | Stock par SKU, alertes, utilisateurs sans licence, export CSV |
| 🗂️ **SharePoint** | Inventaire des sites, bibliothèques documentaires (stockage), export CSV |
| ☁️ **OneDrive** | Lecteurs par utilisateur, quotas (alerte < 5 Go), export CSV |
| 📧 **Exchange** | Utilisation des boîtes (taille, éléments, dernière activité — D30), export CSV |
| 💬 **Teams** | Inventaire des équipes (tout le tenant), canaux, effectifs, export CSV |

- **Licences par utilisateur (v2.1.3+)** : la colonne « Licences » de
  l'onglet Utilisateurs affiche les **noms réels** des licences assignées
  (ex. « Microsoft 365 Business Standard »), traduits depuis les GUID via
  l'inventaire `subscribedSkus`. Nommage conforme au renommage Microsoft
  d'avril 2020 (`O365_BUSINESS_PREMIUM` = Business Standard).
- **Multi-tenant** : bascule entre clients en un clic, reconnexion silencieuse
  au démarrage (cache de tokens chiffré par Windows — zéro mot de passe stocké).
- **Connexion résiliente (v2.1.3+)** : si le client n'a pas encore consenti
  les nouveaux scopes workloads, la connexion réussit quand même en
  « permissions réduites » (onglets SharePoint/OneDrive/Exchange/Teams
  indisponibles, message explicite) — plus jamais d'échec total.
- **Mises à jour automatiques** : au lancement, l'app vérifie les releases
  GitHub en arrière-plan ; si une nouvelle version existe, une notification
  propose la mise à jour — téléchargement avec progression, remplacement du
  .exe et relance automatique (Aide → « Vérifier les mises à jour » pour un
  check manuel).
- **Interface non bloquante** : toutes les opérations Graph en arrière-plan.
- **Fallback device code** automatique (RDP / serveur sans navigateur).

## 📦 Structure

```
graph-tenant-manager/
├── main.py                  Point d'entrée (zéro config)
├── LANCER.bat               Lancement sans compilation (installe Python si besoin)
├── CLIENT.md                Guide client 1 page
├── requirements.txt
├── test_integration.py      153 vérifications
├── .github/workflows/       Build .exe automatique (GitHub Actions)
├── assets/icon.ico          Icône
├── core/                    auth (well-known, silent reconnect), graph_client, async_runner, updater
├── services/                users, groups, devices, licenses, sharepoint, onedrive, exchange, teams
└── gui/                     main_window (9 onglets), dialogs, workload_panels
```

## 🔨 Build du .exe

**Automatique** — chaque push déclenche GitHub Actions (windows-latest,
PyInstaller onefile + icône) → artifact `GraphTenantManager-windows` dans
l'onglet Actions. Un tag `v*` crée une release publique avec l'exe.

**Manuel** (si tu veux compiler chez toi) :
```cmd
pip install pyinstaller
pyinstaller --onefile --windowed --icon assets/icon.ico --add-data "assets;assets" --name GraphTenantManager main.py
```

## 🧪 Tests

```cmd
python test_integration.py
:: 153 vérifications : compilation, imports, AsyncRunner sync+async,
:: auth zéro-config + repli consentement, services mockés (vrai modèle
:: SDK LicenseUnitsDetail), $select users, nommage licences, GUI headless
```

## ⚠️ Limites connues

- 1re connexion : consentement admin exigé par Microsoft (une case, une fois
  par client — aucune app n'y échappe). Sans lui pour les scopes workloads,
  la connexion passe en « permissions réduites » (v2.1.3+).
- Authentification delegated (compte admin) — pas de mode daemon/app-only.
- Listes = pagination complète : très bon jusqu'à quelques milliers d'objets.
- .exe non signé → SmartScreen la 1re fois (cert code signing ~200 €/an).

## 🔐 Sécurité

- Authentification 100 % chez Microsoft (fenêtre officielle) — l'outil ne
  voit jamais les mots de passe.
- Tokens chiffrés par DPAPI (cache MSAL) sur disque, records d'authentification
  locaux uniquement.
- Aucune donnée client stockée — seuls les exports CSV que tu génères.

---
Python 3.10+ · Microsoft Graph SDK · Azure Identity · Tkinter · PyInstaller · GitHub Actions