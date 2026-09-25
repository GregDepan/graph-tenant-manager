# 📦 Guide de Distribution — Graph Tenant Manager

## Vue d'ensemble (v2.0+)

Depuis la v2.0, la distribution est **clé en main** :
- **Aucune app à créer dans Entra ID** — l'outil utilise l'application
  publique multi-tenant de Microsoft (« Microsoft Graph PowerShell »).
- **Aucun config.cfg à éditer** — le tenant est déduit automatiquement du
  compte qui se connecte. (config.cfg reste possible pour surcharger
  clientId/scopes, mais ce n'est plus nécessaire.)
- **Le .exe se met à jour tout seul** (v2.1+) : plus besoin de redéployer
  chez les clients à chaque version — ils reçoivent une notification au
  lancement et l'outil se met à jour (téléchargement + relance auto).

## Méthode de distribution recommandée

1. **Envoyez simplement le lien de téléchargement** :
   https://github.com/GregDepan/graph-tenant-manager/releases
   (le repo est public — le lien marche pour tout le monde)

2. **Ou envoyez un package minimal par email/USB** :
   ```
   GraphTenantManager-package/
   ├── GraphTenantManager.exe    # L'application (release GitHub)
   └── CLIENT.md                 # Guide client 1 page
   ```

3. **Instructions à donner au client** (elles sont dans CLIENT.md) :
   - Double-clic sur l'exe → SmartScreen → « Exécuter quand même »
   - Bouton **Connecter** → compte admin → cocher « Consentement au nom
     de votre organisation » à la 1re connexion
   - C'est tout. Les mises à jour arrivent ensuite automatiquement.

## Cas particuliers

### Client sans navigateur (RDP / serveur)
Rien à faire : à l'échec d'ouverture du navigateur, l'outil bascule
automatiquement en « device code » (code à saisir sur
microsoft.com/devicelogin depuis n'importe quel appareil).

### Client qui refuse le consentement des nouveaux scopes (v2.1+)
L'outil se connecte quand même en « permissions réduites » : les onglets
Utilisateurs/Groupes/Appareils/Licences fonctionnent, seuls les onglets
SharePoint/OneDrive/Exchange/Teams restent bloqués jusqu'au consentement.
Le client peut l'accorder plus tard en se reconnectant et en cochant
« Consentement au nom de votre organisation ».

### Multi-clients sur le même poste (usage MSP)
Connectez les clients l'un après l'autre (bouton Connecter), puis
basculez via le sélecteur de tenant en haut à droite. Au démarrage
suivant, l'outil propose la reconnexion silencieuse de chacun (cache de
tokens chiffré par Windows, zéro mot de passe stocké).

## Build manuel (optionnel)

Le build est automatique via GitHub Actions à chaque push ; un tag `v*`
crée une release publique. Pour compiler manuellement :

```cmd
pip install pyinstaller
pyinstaller --onefile --windowed --icon assets/icon.ico --add-data "assets;assets" --name GraphTenantManager main.py
```

## Versioning

Format sémantique `vX.Y.Z` :
- **Majeure** : refonte/breaking
- **Mineure** : nouvelles fonctionnalités (onglets, scopes…)
- **Patch** : corrections de bugs

À chaque release : bump de `APP_VERSION` dans `core/app_info.py`,
tag `vX.Y.Z` → GitHub Actions construit et publie la release
automatiquement. L'historique détaillé est dans `CHANGELOG.md`.

---

*Graph Tenant Manager v2.1.4*