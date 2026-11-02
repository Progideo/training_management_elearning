# Revue finale locale — E01–E06 et Q00–Q01

Livraison du 2 novembre 2026, branche `feat/e01-e06-elearning` du dépôt distinct.
Un seul addon LGPL-3.0-only, Odoo Community 20 au digest qualifié, TM au commit
`9c9fdcd0bff5ce282602b819fe7165fa6dd4e2d5` inchangé. Les 673 empreintes de fichiers
suivis, le HEAD et l’état propre du checkout métier ont été recontrôlés.

## Résultats constatés

- E01 : import ZIP borné et hostile, fichiers privés, CSP et iframe sur une autre
  origine ; pas de cookie de diffusion, lecture du parent bloquée, faux message
  ignoré et refus des voies natives de téléchargement, y compris jetons de champ.
- E02–E04 : versions publiées immuables, affectations distinctes, tentatives/reprises,
  événements idempotents, refus de révision obsolète, projection et événement dans
  la même transaction. L’échec injecté après projection annule aussi la progression.
  Première réussite conservée, invalidation motivée distincte, nouvelle tentative
  requise après invalidation. Parcours X/Y et provenance S08 conservés.
- E05 : H5P puis SCORM réellement joués dans Chromium, prérequis, reprise, 0/2 →
  1/2 → 2/2, seuil distinct Y non acquis, autre participant inchangé, nouvelle
  tentative vide sans perte de l’acquis, portail natif et historique mobile.
- E06 : 50 sessions HTTP simultanées, 50 écritures et 50 acquisitions persistées,
  aucun doublon malgré rejeux. Sauvegarde p95 1 227 ms, maximum 1 235 ms ; lancement
  p95 2 469 ms, séquence de quatre fichiers p95 7 534 ms. Deux écritures concurrentes
  à même révision retournent 200/409. Suspension native ferme une URL déjà émise.
  Restauration base + filestore exactement identique sur les données contrôlées.
- Q01 : appariement et ordre, 2–8 éléments, barème exact complet ou zéro,
  correction serveur et réponse conservée dans Surveys. Exact, incorrect, vide,
  partiel, reprise, accès croisé, délai, gel/V2 et résultat par thème testés.
  Chromium à 390/320 px : déplacement, effacement, reprise, clavier, correction
  seulement après remise et 100 % final. Captures inspectées.
- Version finale : 16 tests de l’extension lors de la mise à jour, puis 24 tests
  sans échec ni erreur sur base vierge avec contrôles natifs S05/P09/S08 et QCU/QCM.
  L’historique antérieur à Q est comparé ligne par ligne, empreintes des paquets
  incluses ; les 50 acquisitions restent valides.

## Points pour la revue et la mise en service

Les preuves concernent un banc local fictif. Formats effectivement qualifiés :
H5P TrueFalse 1.8 et SCORM 1.2 mono-SCO, pas toutes les bibliothèques/versions.
La charge HTTP ne simule pas cinquante moteurs H5P de navigateur. La recette
clavier/mobile ne remplace pas un audit WCAG. La suite métier complète n’a pas été
rejouée : les points d’intégration cités et les tests de l’extension ont été ciblés.

Les résultats H5P/SCORM restent formatifs et manipulables dans leur environnement
client ; seul l’examen Surveys corrige ses réponses côté serveur. Les capacités
de lecture sont porteuses, courtes et révocables ; les octets déjà reçus ne peuvent
être rappelés. Exploitation : deux origines HTTPS, idéalement domaines enregistrables
distincts, proxy fermé, pas de journal d’URL à jeton, sauvegarde cohérente et recette
de l’environnement cible. Voir `docs/E06.md`.

Aucune fusion, publication distante, migration réelle ni mise en service. Banque
partagée et types Q02/Q03 différés selon le plan. Les documents E00 conservent la
conception initiale ; les documents E01–Q01 décrivent la livraison actuelle.

Les erreurs initiales de recette et leurs corrections restent visibles dans les
preuves des lots. Les copies de journaux masquent les secrets et identifiants de
session. Banc, volumes, réseaux, mots de passe et dump temporaires supprimés après
recette ; contrôle séparé des autres conteneurs dans `q01/cleanup-verification.txt`.
