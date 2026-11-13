# Compatibilité des offres TM et des obligations partagées

Le moteur commun distingue facultatif, requis à passer et requis à réussir.
Les offres TM sélectionnent les versions partagées ; la confirmation d’inscription
fige leurs obligations. L’extension interactive historique continue d’utiliser
ce contexte TM sans créer une seconde progression d’examens.

Le [contrat, les droits et la recette](https://github.com/Progideo/training_management/blob/feat/j2-shared-exam-obligations/docs/j2-shared-exam-obligations.md)
restent dans le dépôt propriétaire du moteur et de l’adaptateur TM.
`compatibility.json` épingle la composition associée ; les preuves réelles restent
dans les PR. Le socle autonome `training_elearning` et son adaptateur Survey restent
à livrer : cette compatibilité ne vaut pas qualification des offres autonomes.

Le [raccordement aux offres autonomes](J3-autonomous-exam-offers.md) poursuit cette tranche sur les modèles Community natifs, sans dépendance métier à TM.
