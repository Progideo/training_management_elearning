# Raccordement au moteur commun d’examens

La passation, le chronométrage serveur, la validation des interactions enrichies
et le calcul exact appartiennent désormais à `training_mock_exam`.
L’extension historique conserve les widgets et pages apprenant raccordés à TM ;
les classes qui dupliquaient les règles du moteur sont supprimées.

Le [contrat et la recette du moteur commun](https://github.com/Progideo/training_management/blob/feat/j1-shared-exam-runtime/docs/j1-shared-exam-runtime.md)
restent dans TM. `compatibility.json` épingle les versions associées. Utiliser ce
contrat pour vérifier sauvegarde, reprise, remise, correction finale et deux
inscriptions indépendantes. Les preuves d’exécution restent dans les PR.

Cette tranche ne livre pas encore `training_elearning_survey` ni les obligations
et la progression autonomes. Aucune migration métier historique ou bascule réelle
n’est qualifiée.
