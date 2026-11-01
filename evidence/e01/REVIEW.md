# E01 — Preuves de sécurité, première étape

Import contrôlé, versions et fichiers immuables, autorisation courte, diffusion
sur deux hôtes, refus des chemins natifs et preview isolée réellement exécutés.
L’autorisation participant sera ajoutée avec les usages/tentatives E02/E03 puis
retestée avant l’activation du lecteur : ce dossier seul ne clôt pas toute R07/R17.

- `install-tests.log` : 6 méthodes ciblées réussies (résumé Odoo : 8 tests).
- `update-tests.log` : suite après correction du format des versions H5P exportées.
- `browser.log`, `isolation.png` : paquet hostile dans Chromium, DOM/cookies/données
  du portail inaccessibles, cookies de l’origine contenu vides, message forgé ignoré.
- `revoked-file.log` : URL privée déjà émise refusée après désactivation de l’auteur.
- Test ORM de jeton binaire valide : résolution native possible, diffusion refusée
  au dernier point de conversion. Aucun accès aux octets via `/web/content`.

Erreurs conservées : Chromium headless-shell absent (emploi du Chromium installé),
proxy sans tous ses chemins temporaires (corrigé), attente de 403 alors que la route
native renvoie volontairement 404 (acceptation du refus sans divulgation).
Ces erreurs de banc ne sont pas masquées par les preuves finales.

Aucune exécution distante. Le même banc isolé sera réutilisé pour les incréments
suivants et supprimé en fin de recette ; aucun autre service n’est modifié.
