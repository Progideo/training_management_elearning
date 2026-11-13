# Résolution d’un incident de notification

Référence : [eLearning #43](https://github.com/Progideo/training_management_elearning/issues/43).

Après une résolution motivée, le formulaire ouvre la notification du nouvel essai.
L’incident précédent reste conservé et le traitement existant conserve ses contrôles
serveur, son destinataire et le départ de la fenêtre contractuelle à l’envoi effectif.
Le formulaire et les états de notification disposent des libellés français.
Le contre-essai a montré que l’identifiant XML ne change pas l’identifiant du champ natif ; la séparation accessible du motif reste à corriger dans J25.

## Recette

1. Avec la coordination, ouvrir une notification fictive en incident puis sa résolution.
2. Saisir un motif et enregistrer : la fiche du nouvel essai doit s’ouvrir.
3. Vérifier l’essai suivant, son état puis la conservation de l’incident précédent.
4. Rejouer l’ancienne résolution : elle doit être refusée sans nouvel envoi.

Le test natif `TestHumanPractical.test_bounce_blocks_closure_and_resolution_restores_full_window`
passe par le vrai formulaire et vérifie l’action retournée, le nouvel essai et le délai
contractuel après transmission. La procédure navigateur reste à contre-vérifier après livraison.
