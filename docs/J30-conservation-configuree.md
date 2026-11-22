# J30 — Conservation configurée hors du module

Décisions du 22 novembre 2026, communes avec Training Management : voir
[conservation configurée](https://github.com/Progideo/training_management/blob/main/docs/conservation-configuree.md).

- Les preuves eLearning restent par défaut. Seul un administrateur (`base.group_system`)
  les supprime, par l'action « Supprimer le dossier » de l'accès apprenant ou par une
  règle qu'il a configurée (Data Recycle, action automatisée). Un parcours en `sudo()`
  d'un autre utilisateur reste refusé ; les droits d'accès ne changent pas.
- Un accès apprenant ne se supprime qu'une fois révoqué ou archivé ; l'action supprime
  ses preuves eLearning (dépôts et fichiers, tentatives, notifications, attestations…),
  jamais les ventes.
- Les protections d'intégrité restent : contenus publiés, éditions avec historique,
  sièges et mandats en cours de vie.

Recette : sur un accès actif, « Supprimer le dossier » est refusé ; après révocation,
l'accès et ses dépôts disparaissent. En gestionnaire eLearning, la suppression d'une
notification est refusée.
