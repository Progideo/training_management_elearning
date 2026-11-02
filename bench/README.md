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

## Banc E01–E06 et Q01 (livraison actuelle)

Les commandes E00 ci-dessus sont l’historique du socle. Pour la livraison actuelle,
utiliser `bench/e01/run` et sa configuration à deux origines, avec le projet
`tm-e01-20261101`. Les addons TM restent montés en lecture seule. Les ports publiés
sont limités à la boucle locale : portail 18269, contenu 18270 ; PG reste privé.
Le banc est supprimé après la recette, volumes inclus. Ne pas utiliser de prune.

Préparer un dossier temporaire privé (`LMS_SECRET_DIR`, mode 0700) contenant
`db_password` aléatoire (mode 0600), puis définir `TM_ADDONS_DIR` vers le checkout
qualifié. Le wrapper contient les chemins locaux de cette recette comme valeurs
par défaut, remplaçables par ces variables. Ne jamais réutiliser un secret réel.

```sh
./bench/e01/run up -d odb
./bench/e01/run run --rm odoo odoo -d q01_fresh --addons-path=/mnt/extra-addons,/mnt/qualification-addons --without-demo --workers=0 --max-cron-threads=0 -i training_management_elearning --test-enable --test-tags "$(cat bench/test-tags)" --stop-after-init
```

Sur une autre base `e01`, installer de même sans les tests puis injecter, une seule
fois et dans cet ordre, `bench/e01/seed.py`, `bench/e05/seed.py`,
`bench/e06/seed_load.py` et `bench/q01/seed.py`, avec le shell Odoo sans HTTP :

```sh
./bench/e01/run run --rm -T odoo odoo shell -d e01 --addons-path=/mnt/extra-addons,/mnt/qualification-addons --no-http < bench/e01/seed.py
./bench/e01/run up -d odoo gateway
```

Chaque seed affiche des identifiants fictifs à reporter dans les fichiers JSON de
recette correspondants : ne pas réutiliser aveuglément les IDs de la qualification.
Les scripts navigateur `bench/e01/browser.cjs`, `bench/e05/*.cjs`,
`bench/e06/security.cjs` et `bench/q01/browser.cjs` utilisent Chromium/Playwright.
Adapter uniquement les chemins du runtime local et le dossier de secrets. Les
passations font évoluer les données : E05 vérifie les prérequis dans l’ordre X/Y ;
ouvrir Y par la coordination après la réussite de X. Le seed de charge E06 et le
seed Q01 sont séparés. La charge E06 utilise 50 contextes HTTP et `verify_load.py`
contrôle leurs écritures réelles. Lire les scripts et leurs assertions avant rejeu.

Pour la restauration, suivre `docs/E06.md` : arrêter les écritures, sauvegarder base
et filestore cohérents, restaurer dans `e01_restore`, comparer les checkpoints et
rejouer `verify_load.py`. La conservation d’historique après Q01 est vérifiée avec
le même checkpoint, en comparant les enregistrements préexistants ; les nouveaux
objets et fichiers d’assets sont admis. Les résultats historiques ne sont pas
réécrits par les mises à jour.

Conserver les résumés de tests, preuves et erreurs de recette. Masquer jetons et
identifiants de session dans les copies de journaux. Après vérification :
`./bench/e01/run down -v --remove-orphans`, suppression du seul dossier temporaire
de secrets/dump, contrôle de l’absence des ressources de ce projet et de l’état
inchangé des autres conteneurs. Ne pas toucher aux autres bancs.

## Revue corrective du 2 novembre 2026

La branche de revue utilise `bench/review/run` (projet `tm-review-20261102`, dossier
secret `/private/tmp/tm-review-20261102-secrets`) et les mêmes images épinglées et
montages métier en lecture seule. Créer le secret temporaire comme ci-dessus.
`bench/review/test-tags` sélectionne l’extension et les classes serveur complètes
S05/P09/S08/Surveys retenues. `bench/review/browser.cjs` réutilise les recettes déjà
livrées avec une destination de preuves distincte et ajoute la reprise H5P immédiate
et les entrées HTTP excessives. Les identifiants sont extraits des nouveaux seeds.
Les deux scripts `parent.test.cjs` et `runner.test.cjs` reproduisent les défauts du
courtier de sauvegarde et de la reprise H5P sans dépendance de temps réel.
`checkpoint.py` complète le checkpoint E06 avec les réponses/résultats Surveys.
Ne pas écraser les preuves de la livraison initiale lors d’un nouveau passage.
