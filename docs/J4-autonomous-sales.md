# Ventes et accès des offres autonomes

Suite de [J3](J3-autonomous-exam-offers.md) et de [#12](https://github.com/Progideo/training_management_elearning/issues/12). Référence : cadrage consolidé du 3 novembre 2026, sections 3 à 5 et D06/D07. Cette tranche livre l’allocation par la coordination ; le portail du représentant mandaté reste à réaliser.

## Intégration native et conditions

`training_elearning_sale` dépend de `training_elearning` et de `sale_management`, sans dépendance métier TM ni obligation d’installer Survey. L’adaptateur Survey reste optionnel ; la composition avec examens permet de vérifier les preuves pédagogiques de bout en bout.

Le code exact Community 20 qualifié de `website_sale_slides` ajoute le client au cours lors de la confirmation et borne l’achat d’un cours à une unité. Les sièges nominatifs et l’autorisation commerciale explicite requièrent donc une intégration ciblée aux produits et lignes de vente natifs. Tarifs, remises, devise, fiscalité, factures, règlements et rapprochements restent natifs. Aucun état comptable parallèle ni paiement spécifique.

Le produit service référence une édition publiée dans sa société exploitante. Il propose six mois calendaires d’accès et trois mois d’attribution, modifiables. La ligne de vente conserve l’édition, les durées et le type d’achat, premier accès ou renouvellement. La confirmation fige la configuration pédagogique de l’édition, même avant activation du premier apprenant. Changer les paramètres du produit n’altère pas les lignes existantes.

La confirmation ne donne aucun accès pédagogique. La coordination commerciale autorise chaque ligne après vérification du règlement ou d’un accord commercial, avec auteur, date et motif. Cette décision ouvre le délai d’attribution. Répéter la décision ne redémarre pas ce délai. Une quantité déjà autorisée ne peut plus être modifiée ; des sièges supplémentaires passent par une nouvelle ligne autorisée.

## Attribution et activation

Une allocation nominative relie la ligne, le bénéficiaire et l’adhésion native unique cours/contact. Les bénéficiaires peuvent être préparés sur le devis, sans accès. Quantités entières, absence de dépassement et échéances sont contrôlées côté serveur sous verrou de la ligne. Aucune réserve mutualisée de crédits.

La coordination utilise l’assistant portail natif pour préparer le compte et son invitation. Il conserve ses contrôles d’identité et d’adresse ; aucune fusion sur le nom, aucun mot de passe attribué par cette extension. L’activation exige l’unique compte Odoo actif du bénéficiaire et sa société autorisée. Elle démarre la durée immédiatement, sans attendre sa première connexion.

Le premier accès fige les obligations via le service existant. Le renouvellement réutilise la même adhésion et ses preuves : il part de la fin actuelle pour un accès actif, sinon de la réactivation. Il exige un historique de la même édition. Un nouvel achat non identifié comme renouvellement ne crée pas une seconde progression sur cette édition. Une suspension ou révocation doit être traitée explicitement avant renouvellement.

Une allocation peut changer de bénéficiaire, ou être supprimée et réattribuée, avant activation. Après activation, son bénéficiaire et ses dates sont conservés. Répéter l’activation ne prolonge pas l’accès et ne double pas la notification. Les modifications après activation passent par les actions motivées de coordination sur l’accès ; elles ne transfèrent jamais les acquis et ne libèrent pas automatiquement un siège.

Une notification d’activation est confiée à la file Odoo. Les erreurs de préparation ou d’envoi détectées créent une activité de coordination sans redater le début effectif de l’accès. La date de fin est contrôlée à chaque requête, indépendamment des tâches planifiées.

L’annulation d’une commande bloque les activations encore en attente ; elle ne supprime ni les accès déjà activés ni leurs preuves. Annulations, avoirs et remboursements exigent une décision explicite sur les droits pédagogiques. Les autres offres, bénéficiaires et contextes conservent leurs propres obligations et états.

## Permissions et recette

Le rôle de coordination commerciale réutilise les droits natifs de gestion des ventes, produits et contacts ainsi que la coordination des cours. Il n’obtient aucun rôle de lecture des réponses d’examen. Les allocations et motifs d’autorisation sont réservés à cette coordination, dans ses sociétés actives. Ni l’acheteur, ni un contact de son entreprise, ni un commercial ordinaire ne reçoit de mandat d’attribution ou de lecture des résultats.

1. Préparer un produit service lié à une édition d’examens publiée ; ajouter deux sièges sur un devis et leurs bénéficiaires.
2. Confirmer : aucun accès. Autoriser une ligne avec motif, puis préparer au besoin le compte par l’assistant portail natif.
3. Activer un siège : vérifier les dates, l’adhésion et les obligations. Répéter l’action : aucun accès ni courriel supplémentaire.
4. Acheter un renouvellement de la même édition : vérifier la prolongation depuis la fin actuelle et la conservation du score, des obligations et de l’échéance d’une tentative en cours.
5. Vérifier le refus au-delà de la quantité ou du délai, depuis une autre société, et pour une ligne non autorisée ou annulée. Annuler une vente activée : ses preuves restent présentes.

Le portail de délégation entreprise, ses mandats et bilans limités restent à raccorder. Les parcours multicours et les dérogations commerciales après échéance restent également hors de cette tranche. Les décisions humaines sur règlement, accord commercial, suspension ou remboursement ne sont pas simulées par une automatisation.
