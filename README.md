# Training Management eLearning

Extension Odoo 20 Community : ressources formatives privées H5P/SCORM,
publication versionnée, affectations, tentatives et reprise, progression native TM,
portail et deux types d’examen blanc — appariement et mise en ordre.

L’addon historique `training_management_elearning`, LGPL-3.0-only, raccorde la
bibliothèque `training_interactive` à TM et à son adaptateur Survey. Les nouveaux
addons `training_elearning` et `training_elearning_survey` livrent les
[offres autonomes composées d’examens](docs/J3-autonomous-exam-offers.md), sur les
cours et adhésions natifs sans dépendance métier à TM. Le [raccordement aux ventes](docs/J4-autonomous-sales.md) ajoute les sièges nominatifs,
l’autorisation commerciale et le renouvellement. Le [portail entreprise](docs/J5-company-mandates.md)
limite consultation et attribution aux achats explicitement mandatés. Les [activités natives](docs/J6-native-course-activities.md) ajoutent PDF, articles, vidéos publiques et prérequis explicites. Les [plans vendus et corrections d’édition](docs/J7-edition-revisions.md) conservent les références et acquis antérieurs. Les ressources interactives autonomes et TP restent à raccorder. Les [lecteurs et examens communs](docs/J1-shared-readers-exams.md)
poursuivent cette extraction. Le [moteur de passation commun](docs/J1-shared-exam-runtime.md)
porte désormais le chronométrage et les réponses. Les [obligations des offres TM](docs/J2-shared-exam-obligations.md)
sont figées par inscription. Voir [la tranche J1](docs/J1-shared-interactive.md)
et la composition exacte de `compatibility.json`. Les lecteurs embarqués gardent
leurs licences ; aucun cœur Odoo n'est modifié.

## Références historiques livrées

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
Les lots E00–E06, Q00–Q01 et les corrections validées sont intégrés dans la branche
principale locale `main` depuis le 2 novembre 2026. L’avance rapide conserve le
contenu revu au commit `a76946c` et tout son historique. Les branches de travail
sont conservées. [Vérifications de fusion](evidence/merge/verification.txt).
Dépôt public : [Progideo/training_management_elearning](https://github.com/Progideo/training_management_elearning).
Voir [organisation et validation](docs/ORGANIZATION.md) et [versions compatibles](compatibility.json).

## Qualification historique

H5P TrueFalse 1.8 via H5PStandalone 3.8.2 ; SCORM 1.2 mono-SCO via scorm-again
3.5.0. Pas de prise en charge générale H5P, SCORM 2004 ou multi-SCO revendiquée.
Ces résultats sont formatifs, sans valeur de preuve d’examen inviolable ni émission
automatique d’attestation. Les examens blancs conservent la correction serveur
native, avec barème exact pour les deux interactions ajoutées.

La campagne historique E06 a éprouvé 50 sessions HTTP simultanées, avec sauvegardes p95 de 1,23 s,
ainsi que leur persistance. Elle ne représente pas 50 navigateurs H5P complets ni
un dimensionnement de production. Pas d’audit d’accessibilité exhaustif, de
migration réelle, de banque partagée ou de types complémentaires Q02/Q03.

La cible consolidée du 3 novembre 2026 retient quelques utilisateurs et la
concurrence ciblée ; les mesures E06 ne sont pas des critères de lancement validés
pour les nouvelles applications séparées.
