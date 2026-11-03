# Adaptateur des lecteurs et examens communs

Suite de [J1 #12](https://github.com/Progideo/training_management_elearning/issues/12).
La [définition de la frontière](https://github.com/Progideo/training_management/blob/feat/j1-shared-readers-exams/docs/j1-shared-readers-exams.md)
reste dans TM, propriétaire des bibliothèques communes.

`training_management_elearning` consomme maintenant les lecteurs et autorisations
courtes de `training_interactive`, ainsi que les définitions enrichies et l’assistant
natif de `training_mock_exam`. Les fichiers tiers, licences et lecteurs ne sont
plus dupliqués dans ce dépôt. Les anciens noms techniques et URLs restent stables.

L’adaptateur conserve les affectations TM, tentatives, sauvegardes idempotentes,
révisions et acquis. Ses points d’extension contrôlent l’inscription, la version et
l’utilisateur à chaque lecture. Le parent commun reçoit l’URL de sauvegarde du
contexte autorisé. Les pages de passation et leur service TM restent ici ;
l’application autonome `training_elearning` n’est pas encore livrée.

L’action native d’édition et les anciens identifiants de vues sont conservés pour
la composition actuelle. Les questions d’appariement et de mise en ordre sont
maintenant définies une seule fois dans le commun ; leur rendu apprenant reste
raccordé au service TM. Aucune seconde authentification ni table de réponses
concurrente de Survey n’est créée.

## Recette courte

1. Utiliser les versions épinglées par `compatibility.json` sur une base fictive.
2. Importer et prévisualiser H5P/SCORM avec un auteur ; lancer une affectation avec
   un apprenant, sauvegarder et reprendre. Refuser le contexte d’un autre apprenant.
3. Retirer une version ; refuser lecture et renouvellement sans effacer l’acquis.
4. Publier un examen enrichi TM, terminer puis refaire une tentative. Vérifier
   évaluations, orientation et attestations existantes après mise à jour.

`ci/validate.sh` vérifie installation et mise à jour ; les régressions du parent
et du runtime chargent les sources du dépôt TM avec `TM_ADDONS_DIR`.
Les preuves réellement exécutées restent dans les PR. Cette tranche ne qualifie
ni migration historique ni bascule vers l’application autonome.
