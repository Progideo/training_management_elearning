# Training Management eLearning

Extension locale Odoo 20 Community : ressources formatives privées H5P/SCORM,
publication versionnée, affectations, tentatives et reprise, progression native TM,
portail et deux types d’examen blanc — appariement et mise en ordre.

Un seul addon `training_management_elearning`, LGPL-3.0-only. Il dépend de
`training_management` et, depuis Q01, de `training_management_survey`. Aucun fichier
métier TM ni cœur Odoo modifié. Les lecteurs tiers embarqués gardent leurs licences.

## Livraison locale

| Lot | Fonction livrée | Documentation et preuves |
| --- | --- | --- |
| E00 | Inventaire privé et contrat d’intégration | [Conception initiale](docs/E00.md), [preuves](evidence/REVIEW.md) |
| E01 | Import borné, fichiers privés, lecture sur origine isolée | [E01](docs/E01.md), [preuves](evidence/e01/REVIEW.md) |
| E02 | Publication, retrait, affectations et usages immuables | [E02](docs/E02.md), [preuves](evidence/e02/REVIEW.md) |
| E03 | Tentatives, reprise, reçus idempotents et lecteurs | [E03](docs/E03.md), [preuves](evidence/e03/update-tests.log) |
| E04 | Projection atomique dans la progression native, parcours et provenance | [E04](docs/E04.md), [preuves](evidence/e04/REVIEW.md) |
| E05 | Entrée et historique dans le portail TM, mobile et clavier | [E05](docs/E05.md), [preuves](evidence/e05/REVIEW.md) |
| E06 | Charge 50 participants, restauration et exploitation | [E06](docs/E06.md), [preuves](evidence/e06/REVIEW.md) |
| Q00–Q01 | Appariement et ordre, correction serveur, versions et historique Surveys | [Contrat](docs/Q00.md), [livraison](docs/Q01.md), [preuves](evidence/q01/REVIEW.md) |

[Revue et corrections du 2 novembre](docs/REVIEW_2026-11-02.md) ·
[Banc reproductible](bench/README.md) · [Revue finale](evidence/FINAL_REVIEW.md).
Livraison initiale sur `feat/e01-e06-elearning` ; revue corrective sur
`fix/review-elearning-20261102`, commits locaux prêts pour revue. Aucune fusion,
publication distante ou mise en production effectuée.

## Périmètre qualifié

H5P TrueFalse 1.8 via H5PStandalone 3.8.2 ; SCORM 1.2 mono-SCO via scorm-again
3.5.0. Pas de prise en charge générale H5P, SCORM 2004 ou multi-SCO revendiquée.
Ces résultats sont formatifs, sans valeur de preuve d’examen inviolable ni émission
automatique d’attestation. Les examens blancs conservent la correction serveur
native, avec barème exact pour les deux interactions ajoutées.

La charge valide 50 sessions HTTP simultanées, avec sauvegardes p95 de 1,23 s,
ainsi que leur persistance. Elle ne représente pas 50 navigateurs H5P complets ni
un dimensionnement de production. Pas d’audit d’accessibilité exhaustif, de
migration réelle, de banque partagée ou de types complémentaires Q02/Q03.
