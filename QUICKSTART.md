# 📘 Guide de Démarrage Rapide

## ⚡ Installation en 2 minutes

### Étape 1 : Télécharger
Téléchargez **`GraphTenantManager.exe`** depuis la page des releases :
https://github.com/GregDepan/graph-tenant-manager/releases

### Étape 2 : Lancer
1. Double-cliquez sur **`GraphTenantManager.exe`**
   - Windows affiche « Windows a protégé votre PC » (SmartScreen, exe non
     signé) → **Informations complémentaires → Exécuter quand même**
2. Cliquez sur **🔐 Connecter**
3. Le navigateur s'ouvre : connectez-vous avec le **compte administrateur**
   du tenant client
4. **À la première connexion uniquement** : cochez
   **« Consentement au nom de votre organisation »** puis **Accepter**
5. Le tenant est reconnu automatiquement — **Bravo ! 🎉**
   (plus aucune saisie de Tenant ID, plus d'app à créer dans Azure)

> Pas de navigateur (RDP, serveur) ? L'outil bascule automatiquement en
> « device code » : ouvrez microsoft.com/devicelogin sur un autre appareil
> et saisissez le code affiché.

> L'outil utilise l'application publique multi-tenant de Microsoft
> (« Microsoft Graph PowerShell ») — la même que le module PowerShell
> officiel. Aucune installation, aucun Python requis.

## 🎯 Première Utilisation

### Voir le Dashboard
L'onglet **📊 Dashboard** affiche :
- Nom de votre organisation, compteurs utilisateurs/groupes/appareils
- Carte des licences avec alertes de stock bas

### Gérer les Utilisateurs
1. Cliquez sur l'onglet **👥 Utilisateurs**
2. La colonne **Licences** montre les licences réelles de chaque
   utilisateur (ex. « ✔ Microsoft 365 Business Standard »)
3. Boutons : créer, modifier, réinitialiser un mot de passe, gérer les
   licences, bloquer/débloquer, supprimer, exporter en CSV
4. Double-cliquez sur un utilisateur pour voir sa fiche complète

### Ajouter un Autre Client (multi-tenant)
1. Cliquez sur **🔐 Connecter**
2. Authentifiez-vous avec le compte admin du nouveau client
3. Utilisez le sélecteur de tenant en haut à droite pour basculer

### Onglets SharePoint / OneDrive / Exchange / Teams
Ils se chargent au premier clic. S'ils affichent « permissions réduites »,
l'admin du client doit re-cocher le consentement organisation lors d'une
reconnexion (Microsoft exige un accord pour ces nouvelles autorisations).

## 🔄 Mises à jour
Au lancement, l'outil vérifie automatiquement les nouveautés : une
notification propose la mise à jour (téléchargement avec progression,
remplacement du .exe et relance automatique). Check manuel :
**Aide → Vérifier les mises à jour**.

## ❓ Dépannage

### « Admin consent required » (AADSTS65001)
→ Vous devez être administrateur du tenant et cocher « Consentement au nom
de votre organisation » à la première connexion. Sans cela, l'outil se
connecte quand même en « permissions réduites » (onglets de base
uniquement).

### Windows bloque le .exe
→ SmartScreen : « Informations complémentaires → Exécuter quand même »
(l'exe n'est pas signé — un certificat de signature coûte ~200 €/an).

### Le navigateur ne s'ouvre pas
→ L'outil bascule automatiquement en « device code » : ouvrez
https://microsoft.com/devicelogin sur n'importe quel appareil et entrez
le code affiché.

### Prochaine ouverture ?
Au démarrage, l'outil propose la reconnexion automatique des tenants déjà
autorisés — un clic, sans ressaisir de mot de passe (tokens chiffrés par
Windows, jamais de mot de passe stocké).

---

*Graph Tenant Manager v2.1.4 — voir `CHANGELOG.md` pour l'historique.*