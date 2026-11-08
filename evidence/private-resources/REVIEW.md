# Qualification locale — 8 novembre 2026

Complément `training_elearning_resources`, version 20.0.1.0.0, empilé sur la PR #59.
Aucun fichier de `addons/training_elearning/` ni des autres addons existants n’a
été modifié. La composition de référence reste épinglée dans `compatibility.json` ;
le nouveau complément est une installation optionnelle, pas une livraison active.

Commande réellement exécutée : `python3 bench/test-resources.py --shared-addons
<composition-qualifiée>/addons --output <sortie-locale-neuve> --full-composition`.
Images et empreintes des sources : [qualification.json](qualification.json).

```text
install: 0 failed, 0 error(s) of 44 tests
update: 0 failed, 0 error(s) of 42 tests
prepare: RESOURCE_PROBE=prepared
preserved: RESOURCE_PROBE=preserved
concurrency: RESOURCE_PROBE=concurrency-passed
restored: RESOURCE_PROBE=preserved
```

Sept nouveaux cas natifs couvrent formats/empreintes après invalidation du cache,
comptes distincts (dont deux comptes du même contact), compte désactivé,
sociétés autorisées, échéance, révocation, prérequis et retrait d’un TP ; fichiers
figés et mutations directes des pièces jointes ; types/URL/taille invalides ;
HTTP authentifié et refus des URL brutes, y compris un ancien jeton public simulé.
Les PNG/JPEG dépassant 1920 pixels conservent leurs octets ; une image d’un cours
non géré reste redimensionnée nativement. ZIP, XLSX, XLS, PNG, GIF et JPEG sont
également téléchargés par le vrai contrôleur HTTP Odoo.

Les régressions existantes sélectionnées couvrent leçons/portail/indisponibilités,
examens autonomes, ventes autonomes et éditions vendues. Les totaux ci-dessus sont
ceux du résultat Odoo, pas le nombre de tests nouveaux. Les scénarios de panne de
notification et de concurrence produisent les erreurs contrôlées attendues.

Le banc conserve une édition attribuée entre deux processus Odoo : plan, dates,
progression zéro et SHA-256 du fichier restent identiques après mise à jour, puis
après restauration PostgreSQL + filestore. Les deux ordres de transactions
concurrentes imposent une nouvelle tentative ; l’activation reprend le fichier
modifié, et une modification après activation est refusée. Aucune progression
n’est créée par consultation ou téléchargement.

Données entièrement fictives, réseau interne sans port publié, aucun cron ou SMTP
exploitable. Les dumps et journaux complets restent locaux. Aucune CI, fusion,
installation sur une base réelle ou intervention sur un serveur actif.

Recette et limites : [ressources privées](../../docs/private-learning-resources.md).
