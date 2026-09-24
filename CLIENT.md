# Graph Tenant Manager — Guide client (1 page)

## Lancer l'outil
1. Double-cliquez sur **GraphTenantManager.exe**
   - Windows peut afficher « Windows a protégé votre PC » (SmartScreen, car
     l'appli n'est pas signée) → cliquez **Informations complémentaires →
     Exécuter quand même**. C'est normal pour tout nouveau logiciel non signé.
2. Cliquez sur **🔐 Connecter**
3. Dans la fenêtre de connexion Microsoft qui s'ouvre :
   - Saisissez votre **compte administrateur** (ex : admin@votresociete.fr)
   - Saisissez votre mot de passe (jamais stocké par l'outil)
4. À la **première connexion uniquement**, Microsoft demande l'autorisation :
   - Cochez **« Consentement au nom de votre organisation »**
   - Cliquez **Accepter**
5. C'est fini — le tableau de bord de votre tenant s'affiche.

## Utiliser l'outil
| Onglet | Ce que vous pouvez faire |
|---|---|
| 📊 Dashboard | Vue d'ensemble : utilisateurs, groupes, appareils, licences |
| 👥 Utilisateurs | Créer, modifier, bloquer, réinitialiser un mot de passe, gérer les licences, supprimer, exporter en CSV |
| 👥 Groupes | Créer, gérer les membres, supprimer, exporter |
| 📱 Appareils | Inventaire des appareils, conformité, export |
| 🔑 Licences | Stock de licences, alertes de stock bas, utilisateurs sans licence, export |

**Plusieurs clients ?** Connectez-vous avec le compte admin du client A,
puis cliquez 🔐 Connecter à nouveau avec le compte du client B : le menu
« Tenant » en haut à droite permet de basculer entre clients en un clic.

**Prochaine ouverture ?** Au démarrage, l'outil propose la reconnexion
automatique — un clic, sans ressaisir le mot de passe.

## Questions fréquentes
**L'outil voit-il mon mot de passe ?** Non. L'authentification se passe
entièrement chez Microsoft (fenêtre officielle Microsoft). L'outil ne stocke
que le jeton d'accès chiffré par Windows.

**Où sont mes données ?** Nulle part : l'outil interroge Microsoft Graph en
lecture/écriture selon vos actions, mais ne stocke aucune donnée client sur
le disque (seuls les exports CSV que VOUS générez).

**Un message « admin consent required » apparaît ?** Il faut être
administrateur du tenant pour la première connexion (consentement
organisationnel exigé par Microsoft).