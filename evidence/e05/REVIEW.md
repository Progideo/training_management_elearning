# E05 — Résultats réels

- `update-tests.log` : douze méthodes, zéro échec/erreur.
- `browser.log` : H5P joué, SCORM bloqué avant H5P, état étape 2 repris, 80/100
  enregistré, nouvelle tentative vide et retour au portail natif.
- `after-x.log` : X à 2/2, pair à 0/2, Y sans acquis ; l’ouverture administrative
  de Y reste nécessaire (`open-y.log`).
- `y-browser.log` : même paquet à 80/100, seuil Y 90, activité non complétée.
- Captures : `native-before.png`, `native-one-of-two.png`, `native-two-of-two.png`,
  `y-threshold-not-met.png`. La capture mobile initiale a précédé le passage au layout Portal.

Les erreurs des sélecteurs de test H5P sont conservées : les noms accessibles
ne sont pas les simples textes visibles. Le script utilise finalement les contrôles
réels de la bibliothèque. Le refus natif des prérequis est HTTP 422, pas 403.
Aucune réussite de test n’est inférée uniquement depuis une capture.
