# Revue E00 — résultats locaux

Branche `feat/e00-foundation`, dépôt Git local distinct, sans remote ni PR distante.
Résultat prêt à relire, aucune fusion ni mise en production. Le code, les contrats
et les scripts sont regroupés dans ce dépôt ; les preuves ne constituent pas une
qualification des futurs lecteurs.

## Changement proposé

Créer l’addon unique et son inventaire éditorial privé, avec identité stable,
archivage et isolation par société. Fixer la conception des versions, usages,
tentatives et événements et les points d’intégration TM. Dépendance minimale TM ;
ni `website_slides`, ni obligation Surveys avant le lot Q. Le parcours participant
et les critères historiques restent ceux de TM.

## Exécution

Image Odoo et PostgreSQL épinglées dans le compose ; TM au commit
`9c9fdcd0bff5ce282602b819fe7165fa6dd4e2d5`, monté en lecture seule. Journaux horodatés
UTC le 1er novembre 2026. Toutes les identités et données du banc sont fictives.

| Vérification | Preuve et résultat |
| --- | --- |
| Installation vierge E00 + Surveys | `install.log` : registre chargé, vues et ACL chargées, arrêt normal |
| Première mise à jour et tests E00 | `update-1-tests.log` : 3 méthodes, zéro échec/erreur |
| Seconde mise à jour | `update-2.log` : registre chargé, arrêt normal |
| Conservation | `before-update.json`, `after-update-1.json`, `after-update-2.json` identiques : ressource, programme, réalisation, inscription, deux activités, progression native 1/2, identifiants XML |
| Installation finale et coexistence | `fresh-native-tests.log` : 9 méthodes ciblées lancées ; résumé Odoo « 0 failed, 0 error(s) of 11 tests » (comptage du framework conservé tel quel) |
| Installation sans Surveys | `minimal-install-tests.log` : 3 méthodes E00 lancées, résumé Odoo 0 échec/erreur sur 5 tests ; dépendance minimale vérifiée |
| Intégrité métier | `integrity.log`, `tm-before.json`, `tm-after.json` : 673 fichiers suivis identiques, HEAD identique, checkout propre |

Les neuf méthodes couvrent trois contrôles E00, la déclaration/prérequis S05,
les acquis P09, la distinction de preuve S08 et trois cas Surveys (publication,
QCM exact/vide/partiel, échéance serveur). La liste exacte est dans `bench/test-tags`.
Le test de formulaire utilise le véritable helper Odoo `Form` ; aucun essai visuel
navigateur, accessibilité ou charge n’est revendiqué pour E00.

## Ajustements et limites observées

La première mise à jour ne lance que les tests du module mis à jour, malgré la
sélection de tags TM/Surveys : trois tests réellement exécutés, pas neuf. La
coexistence a donc été vérifiée séparément en installant les trois modules sur
`e00_tests`. Aucun échec de test ou erreur d’installation masqué. L’avertissement
`markdown2 is not installed` vient de l’image pour le rendu Markdown des messages ;
ce socle ne l’utilise pas. Les journaux bruts sont conservés.

Les versions publiées, affectations et tentatives sont **conçues, pas codées** en E00.
Le socle ne permet ni chargement ni lecture de paquet ; l’isolation du JavaScript
n’est donc pas prouvée. Pas de projection formative, attestation automatique,
questions enrichies, migration de prototypes ou compatibilité H5P générale.
La suite complète TM n’a pas été exécutée ; seule la non-régression ciblée ci-dessus.
E01 doit prouver l’isolation avant d’ouvrir les lecteurs ; voir `docs/E00.md`.

## Nettoyage

`cleanup.log` : projet E00 arrêté et supprimé, volumes/réseaux dédiés retirés,
secret temporaire supprimé. Les 14 autres conteneurs gardent leur état initial.
Aucun prune, SSH, déploiement distant ou modification du dépôt métier.
