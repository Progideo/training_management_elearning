# Organisation des dépôts et des livraisons

- `Progideo/training_management` : socle, Ventes, Surveys et Website. Ce dépôt reste inchangé dans cette réorganisation.
- `Progideo/training_management_elearning` : un addon dédié, ses lecteurs, interactions, tests et documentation générique.
- `Progideo/neopro_odoo_operations` (privé) : versions effectivement déployées, environnements et procédures NeoPro. Aucun secret, export métier ou sauvegarde dans Git.

L’option fiscale reste facultative à son emplacement actuel. L’extraction fiscale et la séparation des interactions de questions sont différées jusqu’à un besoin d’installation indépendant. Les prototypes historiques ne sont pas des composants distribués.

## Compatibilité et validation

`compatibility.json` fixe le commit TM, les addons requis et l’image Odoo qualifiés. Le workflow `Validation eLearning` récupère cette révision en lecture seule, exécute les régressions JavaScript, puis une installation vierge et une mise à jour avec les tests eLearning et les contrats natifs sélectionnés. Une troisième base installe Website, dont le gabarit de portail diffère, et rejoue les tests eLearning. Les résumés Odoo doivent être présents, non vides et sans échec. Les journaux sont conservés comme artefacts GitHub.

Ce contrôle ne remplace ni les recettes navigateur et de charge, ni une répétition de restauration ou une migration sur copie des données de l’environnement cible. Ces procédures restent dans `bench/README.md` et la documentation des lots.

Chaque changement de compatibilité passe par une branche et une revue. Les livraisons conservent les noms techniques des addons. Un déploiement choisit des commits exacts des deux dépôts ; une branche `main` mobile n’est pas une référence de déploiement.

## Suivi

Le Project d’organisation nº 1 sert au suivi commun, avec des vues par dépôt et une vue de livraison. Les besoins restent dans les issues du dépôt responsable ; les changements et résultats d’exécution dans les PR. Les informations d’exploitation privées restent dans le dépôt privé.

L’automatisation documentée dans Training Management ne couvre que ce dépôt. Sa portée n’est pas élargie implicitement ; le statut des nouveaux dépôts peut être géré manuellement dans le tableau commun.
