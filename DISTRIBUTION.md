# 📦 Guide de Distribution - Graph Tenant Manager

## 🎯 Objectif
Ce guide explique comment distribuer Graph Tenant Manager à vos clients ou collègues.

---

## 📋 Deux Options de Distribution

### Option A: Exécutable Autonome (Recommandé)

**Avantages:**
- ✅ Aucune installation Python requise
- ✅ Fichier .exe unique
- ✅ Prêt à l'emploi
- ✅ Idéal pour clients non-techniques

**Inconvénients:**
- ⚠️ Fichier plus gros (~50-100 MB)
- ⚠️ Nécessite de compiler sur une machine Windows

#### Étapes:

1. **Compiler l'application**
   ```cmd
   cd graph-tenant-manager
   build.bat
   ```

2. **Récupérer les fichiers**
   - Dossier: `dist/`
   - Fichier principal: `GraphTenantManager.exe`
   - Script: `lancer.bat`
   - Config: `config.cfg` (à éditer)

3. **Préparer le package**
   ```
   Graph-Tenant-Manager-Client/
   ├── GraphTenantManager.exe    # Application
   ├── lancer.bat                 # Lanceur
   ├── config.cfg                 # Configuration (avec Client ID du client)
   └── README-CLIENT.md           # Guide utilisateur simplifié
   ```

4. **Configurer pour le client**
   - Éditez `config.cfg` avec le Client ID Azure DU CLIENT
   - OU: laissez le client le faire (voir section "Configuration Client")

5. **Distribuer**
   - ZIPpez le dossier
   - Envoyez par email/WeTransfer/Teams
   - OU: copiez sur clé USB

---

### Option B: Scripts Python (Développement)

**Avantages:**
- ✅ Plus léger
- ✅ Facile à modifier
- ✅ Code source accessible

**Inconvénients:**
- ⚠️ Nécessite Python installé
- ⚠️ Plus complexe pour l'utilisateur final

#### Étapes:

1. **Préparer le dossier complet**
   ```
   graph-tenant-manager/
   ├── main.py
   ├── config.cfg.example
   ├── requirements.txt
   ├── install.bat
   ├── start.bat
   ├── core/
   ├── gui/
   ├── services/
   ├── utils/
   └── README.md
   ```

2. **Supprimer les dossiers inutiles**
   - `build/` (si existe)
   - `dist/` (si existe)
   - `logs/` (sera recréé)
   - `venv/` (sera recréé)

3. **Distribuer**
   - ZIPpez le dossier
   - Le client exécute `install.bat`

---

## 🔐 Configuration Client

### Méthode 1: Vous Configurez (Recommandé)

1. **Récupérez le Client ID du client**
   - Demandez au client de vous envoyer:
     - Application (client) ID
     - (Optionnel) Tenant ID

2. **Éditez config.cfg**
   ```ini
   [azure]
   clientId = a1b2c3d4-e5f6-7890-abcd-ef1234567890
   tenantId = common
   ```

3. **Distribuez avec le fichier déjà configuré**

### Méthode 2: Le Client Configure

1. **Fournissez le fichier `config.cfg.example`**

2. **Envoyez les instructions:**
   ```
   1. Renommez config.cfg.example en config.cfg
   2. Ouvrez config.cfg avec le Bloc-notes
   3. Remplacez VOTRE_CLIENT_ID_ICI par votre Client ID Azure
   4. Sauvegardez
   ```

3. **Fournissez le guide de configuration Azure**
   - Voir section "Configuration Azure" dans README.md
   - OU: envoyez QUICKSTART.md

---

## 📧 Email Type pour Distribution

### Objet: Graph Tenant Manager - Application de Gestion Microsoft 365

```
Bonjour [Client],

Voici l'application Graph Tenant Manager pour gérer votre environnement Microsoft 365.

📦 PIÈCE JOINTE: Graph-Tenant-Manager.zip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 INSTALLATION RAPIDE:

1. Dézippez le dossier sur votre bureau
2. Double-cliquez sur "install.bat"
3. Attendez la fin de l'installation
4. Lancez "start.bat"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚙️ CONFIGURATION OBLIGATOIRE:

Avant la première utilisation, vous devez configurer 
l'application avec votre compte Azure:

1. Lisez le fichier QUICKSTART.md (guide étape par étape)
2. Créez une application dans le portail Azure
3. Copiez le Client ID dans config.cfg

Temps estimé: 10 minutes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 DOCUMENTATION:

- README.md: Documentation complète
- QUICKSTART.md: Guide de démarrage rapide
- Aide en ligne: Menu "Aide" dans l'application

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❓ BESOIN D'AIDE?

Si vous rencontrez des problèmes:
- Vérifiez les logs dans le dossier "logs"
- Répondez à cet email avec les erreurs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cordialement,
[Votre Nom]
```

---

## 🎨 Personnalisation (Optionnel)

### Changer le Nom de l'Application

1. **Éditez `build.bat`**
   ```batch
   --name "VotreNomApplication"
   ```

2. **Éditez `main.py`**
   ```python
   root.title("Votre Nom d'Application")
   ```

3. **Re-compilez**
   ```cmd
   build.bat
   ```

### Ajouter un Logo/Icone

1. **Préparez un fichier .ico**
   - Taille: 256x256 pixels
   - Format: Windows Icon (.ico)

2. **Éditez `build.bat`**
   ```batch
   --icon=votre-logo.ico
   ```

3. **Re-compilez**

### Personnaliser les Couleurs

1. **Éditez `gui/main_window.py`**
   - Cherchez `_setup_styles()`
   - Modifiez les couleurs

2. **Exemple:**
   ```python
   style.configure('Title.TLabel', 
       font=('Segoe UI', 16, 'bold'),
       foreground='#0078D4')  # Bleu Microsoft
   ```

---

## 📊 Suivi des Versions

### Versioning

Utilisez un système de version sémantique:
- **v1.0.0**: Version initiale
- **v1.1.0**: Nouvelles fonctionnalités
- **v1.0.1**: Correction de bugs

### Journal des Modifications

Créez un fichier `CHANGELOG.md` pour chaque client:
```markdown
# Changelog - Client [Nom]

## v1.0.0 - 2026-01-15
- Installation initiale
- Configuration avec Client ID: xxxxxxxx
- Premier déploiement
```

---

## 🔒 Sécurité & Bonnes Pratiques

### À FAIRE:
- ✅ Utilisez des Client IDs uniques par client
- ✅ Ne partagez jamais les fichiers de config entre clients
- ✅ Révoquez les accès si l'application n'est plus utilisée
- ✅ Gardez une copie des configurations clients

### À NE PAS FAIRE:
- ❌ N'utilisez PAS le même Client ID pour tous les clients
- ❌ Ne commitez PAS config.cfg dans Git
- ❌ Ne distribuez PAS avec des permissions excessives
- ❌ N'envoyez PAS les identifiants par email non-sécurisé

---

## 📞 Support Client

### Questions Fréquentes

**Q: L'application ne se lance pas**
→ Vérifiez que Python est installé (Option B) ou que le .exe n'est pas bloqué par l'antivirus

**Q: Erreur de connexion**
→ Vérifiez que le Client ID est correct et que les permissions Azure sont accordées

**Q: Comment ajouter un nouveau tenant?**
→ Cliquez sur "🔐 Connecter" dans l'application

**Q: Puis-je utiliser l'application sur plusieurs PC?**
→ Oui, copiez simplement le dossier `dist` complet

### Checklist de Dépannage

- [ ] Python installé (Option B)?
- [ ] Client ID correct dans config.cfg?
- [ ] Permissions Azure accordées?
- [ ] "Allow public client flows" activé?
- [ ] Firewall/Antivirus ne bloque pas l'application?

---

## 📈 Améliorations Futures

### Fonctionnalités Demandées par les Clients

- [ ] Export PDF des rapports
- [ ] Notifications email automatiques
- [ ] Synchronisation planning
- [ ] Interface web
- [ ] API REST

### Recueillir les Feedbacks

Après 1 semaine d'utilisation:
1. Envoyez un email de suivi
2. Demandez:
   - Qu'est-ce qui fonctionne bien?
   - Quels problèmes rencontrés?
   - Quelles fonctionnalités manquantes?
3. Notez les feedbacks pour la v2.0

---

## 🎯 Résumé

**Pour distribuer rapidement:**

1. Compilez: `build.bat`
2. Configurez: Éditez `config.cfg` avec le Client ID du client
3. Packagez: ZIPpez le dossier `dist`
4. Envoyez: Email avec pièce jointe + instructions
5. Suivez: Email de feedback après 1 semaine

**Temps total**: ~15 minutes par client ⚡

---

**Bon déploiement! 🚀**
