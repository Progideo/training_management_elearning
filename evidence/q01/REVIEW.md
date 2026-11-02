# Q01 — Revue locale

Les quatre tests initiaux passent : barème exact pour les deux types, quatre
passations exact/partiel/incorrect/vide, reprise, thème et historique ; contraintes
bijectives, accès croisé et délai ; publication, gel, V2 et données de rendu sans
solution. La suite finale et l’installation vierge sont consignées séparément.

Le premier script navigateur ciblait aussi le bouton de déconnexion : sélecteur
corrigé (`browser-first-selector-error.log`). Le deuxième sélectionnait avant le
chargement des interactions (`browser-first-save-error.log`) : attente de
l’initialisation dans la recette et listes désactivées jusqu’à l’initialisation
dans le produit. Aucun succès de sauvegarde n’a été inventé.

`browser.log` contient la passation complète réussie ; les captures montrent
l’appariement à 390 px, l’ordre à 320 px et le résultat final. Les images ont été
inspectées. Les contrôles portent sur la reprise après rechargement, le déplacement
d’un élément déjà utilisé, l’effacement, le clavier, l’absence de débordement et
le résultat natif à 100 %. L’explication privée n’est présente qu’après remise.

Les journaux sont fictifs ; les identifiants de dispositif/session éventuellement
journalisés par Odoo sont masqués dans les copies conservées. Aucun mot de passe,
jeton de diffusion ni dump n’est destiné au dépôt. Aucun checkout TM modifié.

## Résultat final

- Mise à jour sur données existantes : 16 tests, zéro échec/erreur.
- Installation vierge de l’addon avec ses dépendances : 24 tests, zéro échec/erreur
  (`fresh-native-tests.log`), dont contrôles natifs S05/P09/S08 et Surveys.
- Navigateur final après verrouillage des listes pendant l’initialisation :
  `browser-final.log`, passation réussie, résultat 12/12 et 6/6 par thème.
- Toutes les lignes historiques E06 et empreintes des paquets conservées après Q
  (`historical-comparison.txt`) ; les 50 acquisitions recontrôlées.
- 673 fichiers métier identiques et checkout TM propre (`tm-unchanged.txt`).
