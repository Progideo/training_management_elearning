# Training Management eLearning

Communiquer en français. L’adaptateur interactif TM réside dans le dépôt TM ; ce dépôt porte trois addons
autonomes et le complément optionnel `training_elearning_resources`, avec sept addons dans TM. Licence LGPL-3.0-only, Odoo Community 20
au digest qualifié dans bench/compose.yaml. Lire docs/J1-shared-interactive.md puis les références E00 utiles ; les
prescriptions historiques contradictoires sont remplacées par le cadrage du 3 novembre.
Développer sur branche dédiée ; préparer une revue avant fusion. Pas de fusion
ni déploiement sans autorisation. Ne pas modifier le cœur Odoo. Les composants communs sont extraits dans le dépôt
TM sur branches coordonnées, sans dépendance métier croisée dans la cible.
Ne pas copier les prototypes en production. Le miroir sources/ est en lecture seule.
Tests réels proportionnés, profils restreints et isolation multi-société.
Secrets et données réelles exclus. Distinguer contrat cible et fonctions livrées.
