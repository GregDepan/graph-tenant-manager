# 📘 Guide de Démarrage Rapide

## ⚡ Installation en 5 Minutes

### Étape 1: Télécharger
Téléchargez le dossier `graph-tenant-manager` complet.

### Étape 2: Installer Python (si pas déjà fait)
1. Allez sur https://www.python.org/downloads/
2. Téléchargez Python 3.10 ou supérieur
3. **IMPORTANT**: Cochez ✅ "Add Python to PATH" pendant l'installation
4. Cliquez sur "Install Now"

### Étape 3: Installer l'Application
1. Ouvrez le dossier `graph-tenant-manager`
2. Double-cliquez sur **`install.bat`**
3. Attendez la fin de l'installation (2-3 minutes)
4. Une fenêtre DOS s'ouvre avec les instructions

### Étape 4: Configurer Azure (Obligatoire!)

#### A. Créer l'application dans Azure
1. Ouvrez votre navigateur
2. Allez sur https://entra.microsoft.com
3. Connectez-vous avec votre compte administrateur Microsoft 365
4. Allez dans: **Identity → Applications → App registrations → New registration**
5. Remplissez:
   - **Name**: `Graph Tenant Manager`
   - **Supported account types**: `Accounts in any organizational directory`
6. Cliquez sur **Register**

#### B. Récupérer le Client ID
7. Sur la page d'overview, copiez **Application (client) ID**
   - Exemple: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`

#### C. Activer les permissions
8. Cliquez sur **API permissions** (menu gauche)
9. **Add a permission** → **Microsoft Graph** → **Application permissions**
10. Ajoutez:
    - `Directory.Read.All`
    - `User.Read.All`
    - `Group.Read.All`
    - `Device.Read.All`
11. Cliquez sur **Grant admin consent for [Your Tenant]**
12. Cliquez sur **OK**

#### D. Configurer l'authentification
13. Cliquez sur **Authentication** (menu gauche)
14. Section **Advanced settings**
15. **Allow public client flows**: `Yes`
16. Cliquez sur **Save**

#### E. Mettre à jour config.cfg
17. Ouvrez le dossier `graph-tenant-manager`
18. Ouvrez **`config.cfg`** avec le Bloc-notes
19. Remplacez `VOTRE_CLIENT_ID_ICI` par le Client ID copié à l'étape B
20. Sauvegardez et fermez

### Étape 5: Lancer l'Application
1. Double-cliquez sur **`start.bat`**
2. L'interface graphique s'ouvre!
3. Cliquez sur **🔐 Connecter**
4. Saisissez votre **Tenant ID** (copié depuis https://entra.microsoft.com → Overview)
5. Le navigateur s'ouvre pour authentification
6. Connectez-vous et acceptez les permissions
7. **Bravo!** Vous êtes connecté! 🎉

---

## 🎯 Première Utilisation

### Voir le Dashboard
- L'onglet **📊 Dashboard** affiche:
  - Nom de votre organisation
  - Nombre d'utilisateurs
  - Nombre de groupes
  - Nombre d'appareils

### Gérer les Utilisateurs
1. Cliquez sur l'onglet **👥 Utilisateurs**
2. (Fonctionnalité en cours de développement dans v1.0)

### Ajouter un Autre Tenant
1. Cliquez sur **🔐 Connecter**
2. Saisissez le Tenant ID du nouveau client
3. Authentifiez-vous
4. Utilisez le dropdown en haut à droite pour switcher

---

## 🛠️ Créer un Exécutable (.exe)

Pour distribuer l'application sans installer Python:

1. Ouvrez une invite de commandes dans le dossier
2. Exécutez: **`build.bat`**
3. Attendez 2-3 minutes
4. Récupérez **`GraphTenantManager.exe`** dans le dossier `dist`
5. Copiez tout le dossier `dist` vers n'importe quel PC Windows
6. Lancez `GraphTenantManager.exe` - ça marche sans Python!

---

## ❓ Problèmes Courants

### "Python n'est pas installé"
→ Téléchargez et installez Python depuis python.org

### "Module not found"
→ Ré-exécutez `install.bat`

### "Erreur d'authentification"
→ Vérifiez que:
- Le Client ID dans config.cfg est correct
- Les permissions sont accordées dans Azure
- "Allow public client flows" est sur Yes

### "Tenant ID non reconnu"
→ Le Tenant ID se trouve dans:
https://entra.microsoft.com → Identity → Overview → Tenant information

---

## 📞 Besoin d'Aide?

1. **Lisez le README.md** - Documentation complète
2. **Vérifiez les logs** dans le dossier `logs`
3. **Consultez** https://learn.microsoft.com/graph/

---

**Prochaine étape**: Connectez votre premier tenant et explorez le dashboard! 🚀
