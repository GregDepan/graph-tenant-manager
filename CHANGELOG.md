# Changelog — Graph Tenant Manager

## v2.1.3 (25/09/2026) — Licences par utilisateur + connexion résiliente

### 🔑 Licences affichées par utilisateur
- L'onglet Utilisateurs affiche maintenant les **noms des licences
  assignées** dans la colonne « Licences » (« ✔ Microsoft 365 E3 ») au
  lieu d'un simple ✔/✖. Les GUID sont traduits en noms commerciaux via
  l'inventaire `subscribedSkus` (chargé en même temps que les users).
- Sans licence : « ✖ Aucune ». Colonne élargie (220 px).
- Le dialogue de détails utilisateur (double-clic) affiche aussi les
  noms complets au lieu des GUID bruts.

### 🔐 Fix « ajout de tenant cassé »
- Cause : les 6 nouveaux scopes v2.1 (SharePoint/OneDrive/Exchange/
  Teams) exigent un **consentement admin** chez le client. Tant qu'il
  n'est pas accordé, AAD refusait **toute** la connexion (AADSTS65001).
- Désormais : tentative complète → si refus de consentement, **repli
  automatique en permissions réduites** (scopes cœur v2.0 déjà
  consentis) : la connexion réussit, les onglets workloads affichent un
  message explicite au lieu d'une erreur Graph brut.
- La reconnexion silencieuse ne casse plus avec les caches v2.0 (11
  scopes) : elle se replie aussi sur les scopes cœur au lieu d'échouer.
- Fix silencieux : `reconnect_silent` pouvait retourner `None` (cache
  expiré) et la GUI enregistrait quand même un tenant cassé →
  désormais contrôlé + message clair.
- Barre de statut : « 🟢 En ligne (permissions réduites…) » quand les
  onglets workloads ne sont pas accessibles.

## v2.1 (25/09/2026) — Workloads M365 + mises à jour automatiques

### 🔄 Mises à jour automatiques
- Au lancement (800 ms après le splash, non bloquant), l'app interroge
  `releases/latest` du repo GitHub et compare le tag à sa version.
- Si une version plus récente existe : notification → téléchargement avec
  barre de progression → remplacement du .exe (schéma `.old`, le binaire
  en cours étant verrouillé par Windows) → relance automatique.
- Check manuel : Aide → « Vérifier les mises à jour ».
- Zéro dépendance (stdlib urllib) ; silencieux si GitHub est injoignable.
- Requiert le repo **public** (sinon les téléchargements seraient bloqués).

### 🚀 4 nouveaux onglets
- **🗂️ SharePoint** : inventaire des sites du tenant (`/sites/getAllSites`,
  pagination complète), bibliothèques documentaires par site avec
  stockage utilisé/quota, export CSV. Sites personnels exclus par défaut
  (option pour les inclure).
- **☁️ OneDrive** : lecteurs personnels par utilisateur
  (`/users/{id}/drive`), quotas consommés/totaux/restants, alerte rouge
  quand il reste moins de 5 Go, export CSV.
- **📧 Exchange** : rapport d'utilisation des boîtes (Reports API
  `MailboxUsageDetail` D30) — taille, nombre d'éléments, dernière
  activité, boîtes supprimées exclues, export CSV. Parsing durci : les
  colonnes sont localisées par intitulé (Microsoft peut les réordonner).
- **💬 Teams** : inventaire des équipes de **tout le tenant** (via
  `groups?filter=resourceProvisioningOptions/any(x:x eq 'Team')` — pas
  seulement celles dont l'admin est membre), canaux avec type
  (standard/privé/partagé), nombre de membres via `$count`, export CSV.

### 🔐 Scopes
- 6 scopes ajoutés pour les workloads : `Sites.Read.All`,
  `Files.Read.All`, `Reports.Read.All`, `Team.ReadBasic.All`,
  `Channel.ReadBasic.All`, `TeamMember.Read.All`.
- Les tenants déjà connectés doivent se **reconnecter une fois** pour
  consentir aux nouveaux scopes (case admin pas nécessaire : ce sont
  des scopes délégués simples).

### 🧹 Correctifs
- **Licences — crash du bouton « Utilisateurs sans licence »** :
  corruption `super().__initasks__` (génération de code) + colonne
  `'de pt'` invalide + `ok_btn` accédé avant construction par
  `BaseDialog`. Corrigé ; ajout de tests d'instanciation des dialogues
  (le trou qui avait laissé passer le bug).
- Tests : 81 → **113 vérifications** (workloads mockés, GUI 9 onglets,
  déconnexion qui vide les panneaux).

## v2.0 (24/09/2026) — CLÉ EN MAIN

### 🚀 Zéro configuration
- **Plus aucune application à créer dans Entra ID** : l'outil utilise
  l'application publique multi-tenant « Microsoft Graph PowerShell » de
  Microsoft (client ID well-known `14d82eec-…`). Fonctionne chez tous les
  clients, sans toucher au portail Azure.
- **Plus de tenant à saisir** : le tenant est déduit automatiquement du
  compte qui se connecte. Un seul bouton « Connecter » → navigateur → compte
  admin → c'est fini.
- **Fallback device code automatique** : si le navigateur échoue (RDP,
  serveur), un code à saisir sur microsoft.com/devicelogin s'affiche.
- **Reconnexion silencieuse au démarrage** : les tenants déjà autorisés sur
  le poste sont proposés en un clic (cache de tokens chiffré, aucun mot de
  passe stocké).
- `config.cfg` devient **entièrement optionnel** (surcharge avancée
  clientId/scopes si besoin ; absent = défauts well-known Microsoft).

### 📦 Distribution clé en main
- **Build automatique via GitHub Actions** (`.github/workflows/build-windows.yml`) :
  push → .exe Windows compilé (PyInstaller onefile + icône) → artifact
  téléchargeable ; release GitHub automatique sur tag `v*` ; smoke-test de
  l'exe intégré au workflow.
- **`LANCER.bat`** de secours : installe Python via winget si absent, les
  dépendances, puis lance l'app (pour tester sans le .exe).
- **`CLIENT.md`** : guide client 1 page (lancer → connecter → consentement →
  utiliser) incluant l'explication SmartScreen et la FAQ sécurité.
- Icône applicative (assets/icon.ico) intégrée au build.

### 🔧 Technique
- `AsyncRunner.run_in_thread` accepte désormais **coroutines ET fonctions
  synchrones** (l'authentification MSAL est bloquante) — bug latent v1.1
  corrigé (la factory sync était passée à `run()` qui exige une coroutine).
- `_on_tenant_selected` : bascule entre tenants purement mémoire (GUID ↔
  libellé résolus), dashboard rechargé, plus de reconnexion réseau.

### ⚠️ Ce qui reste (imposé par Microsoft / écosystème)
- 1re connexion : l'admin du client coche « Consentement au nom de votre
  organisation » — une fois, inévitable pour toute application.
- .exe non signé → SmartScreen « Exécuter quand même » la 1re fois
  (certificat de signature ~200 €/an, optionnel).

## v1.1 (24/09/2026) — Révision complète du socle technique

### 🔧 Corrections critiques
- **Bug async majeur** : l'app utilisait `asyncio.run()` à chaque requête Graph →
  « Event loop is closed » dès la 2ᵉ opération. Nouveau module `core/async_runner.py` :
  un seul event loop persistant en thread dédié, utilisé par toute l'application.
- **Gel de l'interface** : l'authentification navigateur bloquait le thread Tkinter.
  Toutes les opérations Graph passent désormais en arrière-plan (`run_in_thread`),
  avec boutons grisés et barre de statut pendant les chargements.
- **Pagination absente** : Graph ne renvoie que 100 objets par page ; l'ancien code
  plafonnait donc à 100 utilisateurs/groupes/appareils. Pagination complète via
  `odata_next_link` (avec limite optionnelle).
- **Assignation de licences cassée** : l'ancien code faisait un PATCH invalide.
  Utilisation de la vraie API `POST /users/{id}/assignLicenses` (SDK vérifié).
- **Comptages du dashboard** : `$count=true` + `ConsistencyLevel: eventual`
  (1 requête par compteur, fallback pagination si indisponible).
- **Perf groupes (N+1)** : le listing chargeait les membres de CHAQUE groupe
  (100 groupes = 100 requêtes API). `member_count` retiré du listing ;
  comptage à la demande via `get_member_count()`.
- **Création utilisateur sans UPN** : KeyError → retour propre avec log.
- **Conformité des appareils** : déduite à tort de `account_enabled` → utilise
  désormais `is_compliant` (Conforme / Non conforme / Inconnu).
- `requirements.txt` : `asyncio` retiré (module standard, le paquet pip du même
  nom est un leurre qui casse l'install).
- Scopes config revus (retrait de scopes inutiles, ajout Organization.Read.All,
  AuditLog.Read.All, GroupMember.Read.All).

### ✨ Nouveautés
- **Onglet Licences 🔑** : inventaire complet du tenant (subscribedSkus) avec
  consommées / total / disponibles, alertes visuelles rouges (≤ 2 dispo ou
  ≥ 95 % consommées), liste des utilisateurs sans licence, export CSV.
  Mapping FR d'environ 50 SKU courants (SPE_E3 → « Microsoft 365 E3 », etc.).
- **Dashboard enrichi** : 4 cartes compteur + carte Licences (consommées/total) +
  section Alertes licences. Chargements parallélisés (asyncio.gather).
- **Onglet Utilisateurs complet** : liste avec recherche (serveur si ≥ 3 caractères,
  filtre local sinon), créer / modifier / réinit. MDP (généré) / gérer licences /
  bloquer-débloquer / supprimer (confirmé), double-clic détails, export CSV.
- **Onglet Groupes complet** : filtre par type, créer / membres (dialogue
  d'ajout-retrait avec pick user) / supprimer, export CSV.
- **Onglet Appareils complet** : filtre OS, conformité colorée, export CSV.
- **Dialogues** (`gui/dialogs.py`) : création/modif utilisateur, réinit MDP,
  gestion licences, création groupe, membres, détails, sans-licence.
- **Reconnexion silencieuse** : cache de tokens persistant + AuthenticationRecord
  sérialisé (`~/.graph-tenant-manager/` ou `%LOCALAPPDATA%/GraphTenantManager`) —
  un tenant déjà autorisé se reconnecte sans ressaisir le mot de passe.
- **Tests d'intégration** (`test_integration.py`) : 65 vérifications
  (compilation, imports, AsyncRunner, services avec mock, GUI headless) —
  65 PASS / 0 FAIL.

### 📌 Notes
- Le SDK Python (`msgraph-sdk`), `azure-identity` et `tkinter` sont vérifiés
  installés ; chaque import SDK utilisé a été validé par introspection.
- L'authentification reste en flux delegated (compte admin du client).
- Windows : le cache de tokens est chiffré par DPAPI via MSAL si disponible.