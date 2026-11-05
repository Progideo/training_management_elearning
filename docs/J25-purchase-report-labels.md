# Bilans par achat et motif accessible

Référence : [eLearning #44](https://github.com/Progideo/training_management_elearning/issues/44).

Les synthèses internes montrent la commande native en plus de l’attribution,
du bénéficiaire et de l’édition. La relation est en lecture seule et ne porte
aucun suivi supplémentaire. Les champs du bilan et les délais des offres sont
traduits en français. Les calculs, instantanés, accès et projections du portail
entreprise restent ceux des achats existants.

Dans une fiche de notification, le motif en lecture seule est présenté dans
une section. Son ancien libellé d’entrée partageait l’identifiant natif avec
le champ du dialogue et doublait son nom accessible. Le dialogue garde son
unique libellé natif ; aucune adaptation du cœur ni des widgets Odoo.

## Recette

1. Sous coordination habilitée, comparer deux achats du même bénéficiaire et
   de la même édition : la commande permet de les distinguer.
2. Vérifier les périodes et les états, puis les délais de l’offre en français.
3. Ouvrir la résolution depuis une notification : le champ de saisie doit
   être annoncé une seule fois « Motif ». Annuler sans nouvel envoi.
4. Comparer avec le portail représentant : aucune donnée d’un autre achat
   ni nouveau champ interne n’est projeté.

Validation locale : 18 tests natifs existants de correction humaine et de
bilans par achat réussis ; installation française, libellés effectivement
chargés et vue compilée vérifiés. Contre-essais navigateur après livraison
requis, notamment le nombre effectif de libellés du champ dans le dialogue.
