# Banc E00 local jetable

Prérequis : Docker, images épinglées disponibles, checkout TM au commit de
`docs/E00.md`. Les montages TM et addon sont en lecture seule. Projet exclusif
`tm-e00-20261101`, PostgreSQL sur réseau interne sans port publié ; seul le proxy
facultatif écoute `127.0.0.1:18169`. Aucun envoi externe via le réseau interne.
Ne pas réutiliser ce nom si un banc de ce nom existe déjà.

Créer un répertoire de secrets temporaires hors dépôt, mode 0700, et un fichier
`db_password` aléatoire, mode 0600. Exporter `LMS_SECRET_DIR` et `TM_ADDONS_DIR`
vers ce dossier et les addons métier. `run` contient les chemins locaux par défaut
de la qualification ; ils peuvent être remplacés par ces variables.

Depuis la racine du dépôt :

```sh
./bench/run up -d odb
./bench/run run --rm odoo odoo -d e00_fresh --addons-path=/mnt/extra-addons,/mnt/qualification-addons --without-demo=all --workers=0 --max-cron-threads=0 -i training_management_elearning,training_management_survey --stop-after-init
./bench/run run --rm -T odoo odoo shell -d e00_fresh --addons-path=/mnt/extra-addons,/mnt/qualification-addons --no-http < bench/seed.py
./bench/run run --rm -T odoo odoo shell -d e00_fresh --addons-path=/mnt/extra-addons,/mnt/qualification-addons --no-http < bench/checkpoint.py
./bench/run run --rm odoo odoo -d e00_fresh --addons-path=/mnt/extra-addons,/mnt/qualification-addons --without-demo=all --workers=0 --max-cron-threads=0 -u training_management_elearning --test-enable --test-tags /training_management_elearning --stop-after-init
```

Conserver chaque sortie dans `evidence/`. Répéter le checkpoint après cette mise
à jour, puis refaire `-u training_management_elearning --stop-after-init` sans tests
et un troisième checkpoint. `verify.py` compare les sorties `before-update.log`,
`after-update-1.log`, `after-update-2.log` et l’empreinte initiale du checkout métier.
Les fixtures ne doivent être créées qu’une fois.

Pour vérifier les tests natifs, les modules qui les portent doivent être chargés
en installation/mise à jour ; sélectionner leurs tags pendant la seule mise à jour
de l’extension ne suffit pas. Utiliser une seconde base vierge :

```sh
./bench/run run --rm odoo odoo -d e00_tests --addons-path=/mnt/extra-addons,/mnt/qualification-addons --without-demo=all --workers=0 --max-cron-threads=0 -i training_management_elearning,training_management_survey --test-enable --test-tags "$(cat bench/test-tags)" --stop-after-init
```

Lire le résumé `odoo.tests.result` et les méthodes effectivement lancées, pas seulement
le code de retour. La suite complète TM n’est pas exigée par ce socle sans héritage.
L’ouverture HTTP facultative se fait avec `./bench/run up -d odoo gateway`.

Après conservation des preuves : `./bench/run down -v --remove-orphans`, puis supprimer
uniquement le fichier secret et son dossier temporaires. Ne pas lancer de prune Docker.
Les scripts ne visent aucune base de production, aucun serveur distant.
