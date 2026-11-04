# Portail des achats mandatés

Suite de [J4](J4-autonomous-sales.md), [#19](https://github.com/Progideo/training_management_elearning/issues/19) et du cadrage consolidé du 3 novembre 2026, sections 4, 8 et 11.

## Mandat explicite par achat

La coordination prépare un mandat pour un compte Odoo nommé et une ligne de commande confirmée. Elle fixe sa fin, son motif, le droit de consulter et, séparément, le droit d’attribuer des sièges. L’attribution porte sur une liste de bénéficiaires natifs validés pour ce mandat. Aucun domaine d’adresse, indicateur de société ou lien de parenté entre contacts ne confère un mandat.

L’octroi, son auteur et sa date restent conservés. Les permissions d’un mandat accordé sont immuables ; une modification passe par révocation et nouvel octroi. La révocation est immédiate et motivée. Le compte représentant et le coordinateur responsable doivent rester actifs et habilités dans la société exploitante concernée. Retirer le mandat ne révoque pas les droits déjà accordés aux apprenants.

## Parcours et données

L’entrée native du portail ouvre `/my/learning-purchases`. Le représentant ne consulte que ses achats mandatés : référence, offre, quantité de sièges, bénéficiaires, périodes financées et état d’accès limité à ces périodes. Ni scores, réponses, corrigés, rendus, commentaires, attestations, origine d’acquis ni autres formations ne sont exposés. Les autorisations propres aux commandes et factures natives restent distinctes ; le mandat ne les élargit pas.

Le délai de consultation proposé est de trois mois, configurable sur le produit et figé sur la ligne. La fin effective respecte également la fin du mandat. Après une période financée, le portail affiche sa clôture sans relire l’état actuel de l’adhésion : une prolongation financée par un autre achat ne se révèle pas dans cet inventaire. Les dates sont présentées dans le fuseau du compte. Les bilans de progression figés et exports seront raccordés avec les [compléments validés](elearning-validated-decisions.md), notamment pour la correction tardive.

L’attribution exige un mandat autorisant cette action, une ligne autorisée commercialement, un délai ouvert et un bénéficiaire de la liste validée. Elle utilise les verrous, capacités et services d’activation existants. L’auteur réel de l’attribution et le mandat source sont conservés. Une répétition ne consomme pas un nouveau siège, ne prolonge pas l’accès et ne double pas la notification.

Si le compte est absent, ambigu ou nécessite une intervention, le siège reste réservé et une activité est affectée à la coordination. Le représentant ne peut ni explorer le répertoire global, ni créer un mot de passe, ni voir les autres relations du compte. La préparation d’autres bénéficiaires et la réattribution restent à la coordination dans cette tranche.

## Frontières et recette

Le représentant ne reçoit aucun droit ORM général sur les mandats, allocations, cours, réponses ou contacts. Les routes servent des projections scalaires explicitement limitées. Chaque action recontrôle compte, société, mandat, dates et achat ; les mutations utilisent CSRF et la révocation partage les verrous de l’attribution. Les réponses privées ne sont pas mises en cache.

1. Confirmer une commande, autoriser une ligne et préparer deux bénéficiaires.
2. Accorder un mandat nominatif avec fin et liste validée ; vérifier l’entrée sur l’accueil du portail.
3. Avec ce compte, attribuer un siège puis répéter : vérifier l’unicité et l’audit de l’auteur réel.
4. Avec un compte de la même entreprise sans mandat, une autre société ou un autre mandat d’achat, vérifier le refus sur les liens directs et les actions forgées.
5. Révoquer le mandat : consultation et attribution doivent être immédiatement fermées, sans retirer l’accès de l’apprenant.
6. Renouveler l’adhésion depuis un autre achat : l’ancien mandat conserve seulement les dates de sa propre période. Vérifier la fermeture à l’échéance de consultation.
