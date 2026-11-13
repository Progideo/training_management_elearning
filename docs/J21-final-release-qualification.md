# J21 — Composition complète, génération précédente et restauration

Suite de #19. La qualification sélectionne les dix addons ensemble, avec l’intégration
fiscale régionale optionnelle, sans réactiver P15 ni P17–P19. Elle complète les
installations minimales, l’absence de dépendance métier croisée et les mises à jour
déjà couvertes par la validation autonome.

La référence de génération précédente est épinglée dans `compatibility.json`.
Elle inclut TM `616d2a342540eb7a7dbb8e48d6ecd084bc2fc926` et l’adaptateur historique
`d7d3b976d07831bca2de3c75d6c159308adf7f0d`. Les preuves sont fictives ; aucune donnée
métier externe n’est importée. Les fichiers de référence du projet restent intacts.

La répétition installe les anciens addons, crée des preuves natives d’examens,
de ressources interactives et de gestion encadrée, puis capture chaque colonne
initiale des tables métier et Survey. Le déplacement technique des métadonnées
précède le changement de code. Les colonnes initiales, octets des pièces jointes,
réponses, révisions, délais, états de reprise et menu personnalisé sont comparés
après deux mises à jour. Les contrôles de reprise/fin/nouvelle tentative s’exécutent
dans une transaction annulée pour conserver une référence historique stricte.

Un dump PostgreSQL réel et une archive du filestore sont ensuite restaurés dans
une autre base isolée. Chaque fichier référencé et son empreinte native sont
vérifiés. La sauvegarde antérieure est aussi restaurée avec son ancien code pour
éprouver le retour arrière. Les dumps et archives clairs restent dans un répertoire
jetable et sont supprimés ; les artefacts CI conservent les journaux et verdicts.
Cette preuve applicative ne prétend pas valider un stockage distant d’exploitation
ou le déchiffrement de ses sauvegardes.

La comparaison avec la génération livrée a identifié des correctifs absents de la
branche de séparation : émargement délégué, retrait des marges sans effet,
réémission d’attestation après révocation erronée, bornage des demandes publiques
et examens parallèles. Ils sont réintégrés dans la [composition TM coordonnée](https://github.com/Progideo/training_management/pull/136).
Le moteur et le lecteur communs reçoivent les correctifs transversaux ; aucune
fonction encadrée n’est supprimée pour faciliter la séparation.

Une hypothèse de test de bibliothèque est corrigée : Odoo peut permettre la
recherche d’objets standards publics. La confidentialité est vérifiée sur des
cours et examens privés réels, sans changer leurs permissions.

Deux contrôles CI distincts doivent réussir : validation autonome existante et
composition/restauration complète. Les exécutions locales partielles indiquent leur
phase et ne produisent jamais un verdict « tous les addons qualifiés » lorsqu’elle
n’a pas été exécutée. Aucun navigateur automatisé n’est utilisé.

Recette : installer les applications séparément puis ensemble ; ouvrir les deux
lecteurs avec leurs profils ; mettre à jour sans perte d’historique ; restaurer
base et fichiers ; vérifier les refus croisés, les attestations, l’émargement
et les données d’origine. Les résultats réellement exécutés figurent dans la PR.
Le déploiement et la recette manuelle restent des opérations distinctes.
