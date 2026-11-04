# Corrections de recette du portail et des notifications

Les pages privées de cours, parcours, TP, attestations, activités interactives,
examens et achats mandatés utilisent le paramètre natif `additional_title.translate`
du layout Odoo. Leur titre d’onglet correspond au parcours en français, au lieu
d’exposer le nom technique anglais de la vue. Les textes restent traduisibles.

Recette : ouvrir ces espaces avec un compte francophone autorisé et comparer le
titre de l’onglet au contenu affiché ; vérifier aussi une prévisualisation
et un refus de dépôt. Les habilitations et le contenu des documents sont inchangés.

Les formulaires natifs de correction des TP utilisent aussi le catalogue français pour leurs champs, critères et décisions. Les identifiants techniques et les règles de délai, de révision et de conservation des rendus sont inchangés. Vérifier la file, le retour pédagogique et une demande de révision avec le correcteur affecté.

Les liens d’examen du cours et du choix de nouvelle version ouvrent explicitement
le formulaire Survey natif enrichi. Ils ne doivent pas sélectionner une vue de
diagnostic concurrente (TM #140). Vérifier les deux liens avec un auteur habilité.

Une notification historique peut devenir obsolète après un nouvel achat ou une
prolongation. Le modèle de courriel résout sa destination une seule fois et ne
rend le lien que si cette destination reste valide ([#40](https://github.com/Progideo/training_management_elearning/issues/40)).
Le validateur natif peut ainsi recharger le modèle sans effacer ces événements.
Le contrôle des habilitations avant transport continue de refuser leur envoi.

Recette : conserver une notification ancienne puis activer un second droit sur
la même édition ; mettre à jour le module et comparer les événements et
enveloppes historiques. L’ancien événement n’a ni lien rendu ni droit d’envoi,
le nouveau garde sa destination privée et son contrôle d’envoi.
