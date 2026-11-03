# Raccordement à la bibliothèque interactive commune

Suite de [eLearning #12](https://github.com/Progideo/training_management_elearning/issues/12),
cadrage consolidé du 3 novembre 2026. L'addon historique reste un adaptateur de TM
pendant cette tranche. L'application autonome `training_elearning` et ses deux
intégrations ne sont pas encore livrées.

## Responsabilités

`training_interactive`, dans le dépôt TM, possède les ressources, versions,
fichiers, import/retrait et contrôles ZIP. Les mêmes noms de modèles et identifiants
sont réutilisés par les affectations et tentatives ; aucun paquet n'est dupliqué.
Les anciens imports Python du parseur restent disponibles comme redirections.
Les lecteurs, autorisations, sauvegardes, progression TM, questions enrichies et
interfaces privées restent ici. H5P/SCORM gardent leurs limites et licences.

L'ancien groupe auteur hérite du groupe commun. La coordination hérite du rôle
de gestionnaire de bibliothèque. D32 remplace la règle historique d'E01 : l'auteur
habilité publie directement ; seul le gestionnaire retire, avec motif conservé.
Un auteur du socle commun peut prévisualiser une version autorisée avec le lecteur
isolé existant, sans devenir coordinateur TM. Les contrôles courants de société,
compte actif, retrait et autorisation de diffusion restent nécessaires.

Le socle TM ajoute le point d'extension d'attestation qu'appelait déjà cette
extension. Une ressource formative exclue ne bloque pas le document ; une ressource
explicitement incluse doit être terminée. La preuve dédiée et les autres obligations
humaines restent requises. Aucune présence ni attestation automatique ne résulte
d'un score déclaré par un paquet.

## Composition et limites

La composition exacte est dans `compatibility.json`. La branche part du correctif
`d7d3b976...` de la PR #11, qui reste distincte et non fusionnée. La nouvelle PR est
empilée dessus et dépend de la tranche TM commune. Le contrat quotidien avec TM
`main` doit signaler l'absence du composant tant que cette composition n'y figure
pas ; le contrôle ne doit pas être contourné.

Le découpage cible reste dix addons dans deux dépôts. Les futurs adaptateurs TM,
lecteurs communs et application autonome ne sont pas simulés par ces dépendances.
Les anciennes affirmations E00 excluant website_slides restent historiques :
l'application autonome cible utilisera les cours natifs. Les anciennes mesures
E06 ne deviennent pas des critères de lancement de la nouvelle cible.

## Recette courte

1. Avec la composition épinglée sur base neuve, importer dans la bibliothèque,
   publier avec un auteur, puis sélectionner cette version dans une affectation TM.
2. Prévisualiser, lancer, sauvegarder et reprendre ; conserver les références de
   version, la première réussite et les refus entre participants et sociétés.
3. Vérifier le retrait motivé et les refus des URL natives ; aucun fichier privé
   ne devient public à cause de l'extraction.
4. Émettre manuellement l'attestation avec une ressource exclue, puis vérifier
   qu'une ressource incluse et une obligation humaine inachevées la bloquent.
5. Mettre à jour les deux addons partagés et l'adaptateur, vérifier la conservation
   des UUID, versions, octets, retraits et liens. Aucune conversion historique.

Les tests conservés couvrent le correctif du sélecteur #11. Le test de publication
est amendé explicitement pour D32 ; aucun test existant n'est supprimé. Les résultats
réels et limites restent dans les PR ; pas de fusion ni de déploiement implicites.
