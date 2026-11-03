# Examens partagés dans les offres autonomes

Suite de [J2](J2-shared-exam-obligations.md), issue [#12](https://github.com/Progideo/training_management_elearning/issues/12). Référence : cadrage consolidé validé du 3 novembre 2026, D01/D02 et obligations par contexte.

## Composition livrée

`training_elearning` étend les cours, contenus et adhésions natifs : `slide.channel`, `slide.slide`, `slide.channel.partner`. Il dépend du catalogue et de la bibliothèque interactive communs, sans modèle métier TM. `training_elearning_survey` ajoute les examens via `training_mock_exam` et l’intégration native `website_slides_survey`. L’adaptateur historique reste séparé. L’intégration Sales autonome n’est pas livrée par cette tranche.

Une édition référence une formation du catalogue, reste privée et peut contenir plusieurs versions publiées d’examens de cette formation et société. La même version sert plusieurs offres et les deux applications. Les questions, réponses et identités ne sont pas copiées par offre. La publication refuse les contenus non encore pris en charge : cette tranche livre des cours composés d’examens ; les autres supports restent à raccorder.

## Accès et preuves

La coordination crée l’adhésion native unique cours/contact puis active le compte Odoo du participant avec une date de fin explicite et un motif. Cette activation manuelle ne constitue pas un traitement commercial. L’auto-inscription du créateur, les invitations natives, la complétion manuelle et la certification native ne peuvent pas activer un accès géré. Les cours Community non gérés conservent leur fonctionnement.

La première activation fige les versions et obligations dans `training.elearning.exam.requirement`. Une modification pédagogique après activation nécessite une nouvelle édition. Le renouvellement du même accès conserve son identité, ses références, scores, états et échéances de tentatives. Suspension, révocation et compte désactivé ferment le parcours. Après expiration, les agrégats de progression et scores restent visibles ; questions, réponses détaillées et corrigés sont fermés.

Les obligations sont facultatif, requis à passer ou requis à réussir. Un lancement ne suffit pas. Une tentative terminée, y compris clôturée à expiration, satisfait « à passer ». « À réussir » exige le seuil de la version publiée. Les facultatifs sont exclus du pourcentage et de l’achèvement. La meilleure réussite reste acquise après un échec ultérieur. Aucune attestation automatique.

Les réponses et dates restent dans Survey. Le contexte autonome est `slide.channel.partner:<id>` ; TM utilise `training.enrollment:<id>`. Une tentative active par famille/personne/contexte ; reprises et tentatives illimitées utilisent le moteur et le chronomètre serveur communs. Ni résultat ni droit de lecture ne traverse les deux contextes. La coordination des examens autonomes peut lire ses preuves dans sa société ; l’auteur seul n’a pas ces droits. Les routes natives, fichiers directs et jetons de partage ne contournent pas le portail privé `/my/learning`.

## Recette courte

1. Avec une coordination d’examens autonomes, publier une version commune à choix fixes, puis deux éditions utilisant cette version : « à passer » et « à réussir ».
2. Créer deux accès pour un même contact et activer son compte Odoo avec fin et motif. Ouvrir `/my/learning` avec ce compte.
3. Terminer sans bonne réponse le premier examen : seule son obligation « à passer » est acquise. Réussir le second puis échouer une nouvelle tentative : sa progression reste acquise.
4. Vérifier le refus de changement des obligations après activation et la conservation après renouvellement. À l’expiration, seuls les états et scores restent lisibles.
5. Avec un autre apprenant ou une coordination d’une autre société, vérifier le refus d’accès au cours, aux tentatives et aux fichiers. Vérifier l’absence de certificat et de message automatique de réussite.

`ci/validate-autonomous.py` installe la composition sans aucun addon `training_management*`, exécute les tests natifs, crée de vraies réponses puis compare toutes leurs colonnes après mise à jour. Une dernière phase ajoute volontairement TM et vérifie les contextes et droits distincts sur un même examen et participant. Journaux : `ci-results/autonomous/`. Les tests JavaScript existants complètent les tests Odoo ; ils ne prouvent pas seuls un parcours navigateur.

## Validation exécutée

Sur l’image qualifiée Odoo 20 : installation sans TM (22 tests sélectionnés), mise à jour (20 tests), comparaison exacte des preuves, puis coexistence (1 test). Les 35 tests de l’adaptateur historique et les tests JavaScript existants passent également. Le rendu TM en français a été corrigé et son scénario HTTP rejoué avec succès. Les contrôles Ruff et pylint-odoo des nouveaux addons passent.

Le contrôle Chrome supplémentaire n’a pas été exécuté : le port du réseau Docker interne ne pouvait pas être joint depuis la machine et l’ajout d’une connexion réseau a été refusé par la revue automatique. Les contrôles du portail cités ici sont des tests HTTP réels, sans prétendre à une validation complète dans le navigateur.
