# E06 — Preuves locales

- 50 sessions HTTP participantes simultanées : 50 sauvegardes confirmées, p95
  1 227 ms (cible annoncée < 5 000 ms), maximum 1 235 ms. Lancement p95 2 469 ms ;
  séquence de quatre ressources privées p95 7 534 ms. Voir `load-results.json`.
- Persistance : 50 tentatives indépendantes, 50 événements malgré rejeux, 50
  progressions natives correspondantes (`load-persistence.log`).
- Deux écritures réellement concurrentes à la même révision : 200 et 409, aucun
  écrasement silencieux (`http-security.log`). Refus croisés, preview participant,
  CSRF, CSP et absence de cookie de diffusion contrôlés dans cette même recette.
- Suspension native d’une inscription : un lien de fichier déjà émis est refusé
  immédiatement (`suspended-file.log`). L’inscription fictive a ensuite été rouverte.
- Restauration dans `e01_restore` : base et filestore cohérents ; comparaison exacte
  des versions, usages, octets, événements, tentatives et progressions, ainsi que
  des empreintes du filestore (`restore-comparison.txt`). Les 50 acquisitions
  restaurées sont contrôlées à nouveau (`restored-load.log`).
- Installation vierge avec Surveys : 20 tests, zéro échec ni erreur ; tests natifs ciblés : `fresh-native-tests.log`.

La charge mesure des sessions HTTP, pas cinquante navigateurs complets. Les
passations Chromium et le mobile/clavier relèvent d’E05. Le dimensionnement réel,
TLS/domaines et la mise en service demandent une recette de l’environnement cible.
Le dump de test est conservé uniquement dans le dossier temporaire de secrets et
sera supprimé avec le banc. Aucune donnée réelle ni accès distant.
