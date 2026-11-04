# J15 — Trois addons autonomes, sept addons TM

L’ancien adaptateur `training_management_elearning` rejoint le dépôt TM sous
`training_management_interactive`. Ce dépôt ne contient désormais que
`training_elearning`, `training_elearning_sale` et `training_elearning_survey`.
Les noms des modèles et les historiques existants ne changent pas.

Le [contrat de déplacement technique](https://github.com/Progideo/training_management/blob/feat/j15-final-interactive-adapter/docs/j15-module-layout.md)
précise l’arrêt des services, la sauvegarde cohérente, le transfert des métadonnées,
la mise à jour et le retour arrière. Ne jamais désinstaller l’ancien adaptateur.
Le menu Website est transféré au catalogue commun sans perdre sa personnalisation.

`compatibility.json` fixe la composition courante et les deux générations utilisées
par `ci/validate-module-relocation.py`. La qualification compare les lignes métier,
les pièces jointes de formation, les octets des paquets, l’état de reprise et le menu
après deux mises à jour. Elle vérifie également l’idempotence du transfert.

Recette : installer les trois addons autonomes sans TM ; installer séparément
l’adaptateur TM ; puis tester la coexistence avec le même paquet et des progressions
distinctes. Les résultats exécutés restent dans les PR liées à #19.
