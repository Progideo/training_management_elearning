# E04 — Résultats

La suite de douze méthodes a révélé une erreur de fixture : X et Y utilisaient
le même cours, ce que l’unicité native des parcours interdit. Le jeu a été corrigé
avec un second cours/programme, sans changer TM. Les autres tests avaient réussi.
`progression-recheck.log` : les deux tests E04 passent, zéro échec/erreur.

Vérifiés : seuils X/Y indépendants, réussite conservée après nouvelle tentative
inférieure, validation humaine intacte, invalidation motivée sans réécriture de
l’événement, nouvelle acquisition réservée à une nouvelle tentative, provenance
S08 et disparition du blocage Y en cache dans la transaction de réussite X.
Les protections de contexte des créations internes sont renforcées lors de
l’intégration E05 et couvertes par la recette suivante.
