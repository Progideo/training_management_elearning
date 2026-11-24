# J38 — Karma de fin de cours

Décisions du 24 novembre 2026, communes avec Training Management : voir
[gamification des formations](https://github.com/Progideo/training_management/blob/main/docs/gamification.md).

- Les cours gérés calculent leur achèvement sans le crochet natif de `website_slides` :
  le karma « Cours terminé » n'était jamais crédité. Il l'est désormais, au compte de
  l'apprenant (`learning_user_id`), une fois par accès, selon le réglage natif du cours
  (`karma_gen_channel_finish` ; 0 = aucun karma).
- Un achèvement perdu (invalidation motivée d'un acquis) retire ce karma ; un nouvel
  achèvement le recrédite.
- Supprimer le dossier d'un accès terminé retire le karma du cours par une ligne de
  compensation ; l'historique natif du karma est conservé.
- Le karma n'ouvre aucun accès et ne change ni la progression ni les attestations.

Recette : terminer un cours, vérifier +10 ; invalider l'acquis, vérifier −10 ; révoquer
puis supprimer le dossier d'un cours terminé, vérifier le retour au karma initial.
