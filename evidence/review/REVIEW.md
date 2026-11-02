# Preuves de revue corrective — 2 novembre 2026

Référence initiale : `c808965`. Addon corrigé : `20.0.2.1.0`.
[Constats, corrections et périmètre](../../docs/REVIEW_2026-11-02.md).

## Résultats

- Avant correction : `before-fix-tests.log` reproduit l’acceptation d’un paquet H5P
  incomplet, les structures JSON invalides, le remplacement d’un motif de retrait
  et le dépassement numérique. Résultat attendu de cette phase : 2 échecs et
  5 erreurs sur 5 méthodes, dont sous-cas. Ces journaux ne sont pas un échec final.
- `parent-before.log` et `runner-before.log` reproduisent respectivement la requête
  sans délai maximal et l’absence de réponse dans l’événement H5P de résultat.
  `parent-final.log` et `runner-final.log` réussissent après correction.
- Suite intermédiaire après correction : 22 tests de l’extension réussis.
- Installation vierge et suites élargies : **81 tests, zéro échec/erreur**
  (`expanded-native-tests.log`). Les traces SQL de seuils -1/101 sont les refus
  attendus du test natif de contrainte, pas des erreurs de la suite.
- Version finale sur base déjà utilisée : **80 tests, zéro échec/erreur**
  (`final-native-tests.log`), soit 25 tests de l’extension et 55 tests des classes
  natives ciblées. L’installation vierge inclut aussi des contrôles de chargement ;
  les nombres ne sont donc pas directement ceux de la seule mise à jour.
- `update-comparison.txt` : toutes les versions, usages, tentatives, événements,
  empreintes de paquets, progressions, réponses et résultats Surveys comparés sont
  identiques avant/après mise à jour. Les nouveaux assets générés sont exclus de
  cette comparaison, contrairement aux octets pédagogiques conservés.
- `load-persistence.log` : 50 tentatives, 50 événements malgré rejeux, 50 acquisitions.

## HTTP et navigateur

- `e01/browser.log` : contenu hostile incapable de lire DOM/cookies/données du
  portail ; fichier privé contrôlé ; voie native et origine incorrecte refusées ;
  faux message ignoré.
- `e05/browser.log` : H5P joué, réponse restaurée après rechargement immédiat,
  SCORM avec prérequis/reprise/résultat, progression 2/2, nouvelle tentative vide,
  retour natif et contrôle mobile/clavier.
- `q01/browser.log` : appariement et ordre, reprise partielle, déplacement d’option,
  effacement, correction uniquement après remise et 100 % natif. Écrans 390/320 px
  sans débordement, clavier vérifié ; captures conservées et inspectées.
- `e06/load-results.json` : 50 sessions simultanées et 50 sauvegardes confirmées,
  p95 **1 258 ms**, maximum 1 333 ms (objectif p95 < 5 s). Lancement p95 2 203 ms ;
  quatre fichiers privés successifs p95 7 687 ms. Il s’agit de sessions HTTP.
- `e06/security-final.log` : refus croisés et CSRF, absence de cookie de contenu,
  CSP isolée, écritures concurrentes 200/409 ; JSON profond et nombre excessif
  refusés par 409, sans erreur serveur ni consommation de révision.

Le premier rejeu HTTP après redémarrage a précédé la disponibilité du portail
(`e06/security-startup-error.log`). Le lanceur attend désormais la page de connexion
valide ; le rejeu final réussit. Aucune correction métier n’était nécessaire.

## Intégrité et nettoyage

Les fichiers métier sont comparés à leurs 673 empreintes d’origine, avec contrôle
du HEAD et du checkout propre. Le banc porte le projet distinct
`tm-review-20261102` ; seuls ses ressources et ses secrets temporaires sont supprimés.
Les états des autres conteneurs sont comparés avant/après nettoyage. Voir
`integrity-cleanup.txt`. Les identifiants de session/dispositif des copies de
journaux sont masqués ; aucun secret réutilisable ni dump conservé.

Aucune modification du dépôt `training_management`, fusion ni livraison distante.
Aucun problème détecté lors de cette revue n’est laissé sans correction. Les limites
explicites des formats, de la qualification locale et de l’audit des bibliothèques
restent documentées ; il ne s’agit pas d’une garantie générale de sécurité.
