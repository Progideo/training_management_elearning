# J19 — Notifications ciblées et rappels contractuels

Suite de #19 et de la section 10 du cadrage validé. Le modèle de notification
réutilise les modèles, la file, les activités et les tâches planifiées Odoo.
Il ne décide jamais des accès : les contrôles de chaque requête restent autoritaires.

Les nouveaux événements couvrent l’activation directe d’un cours, l’invalidation
motivée et la révision d’un résultat autonome. Les ouvertures de parcours, nouvelles
affectations de TP, retours individuels et changements d’attestation conservent leurs
notifications typées existantes ; l’ouverture d’un cours par un parcours n’envoie
pas une seconde activation générique. Les métadonnées commerciales d’activation
référencent désormais le message commun, sans deuxième envoi.

Les rappels par défaut sont 30 et 7 jours pour la fin d’accès au cours, la limite
de démarrage des cours restants et la limite d’attribution des sièges restants ;
3 jours pour une révision de TP attendue ; un jour ouvré avant une correction ;
une alerte à dépassement à la coordination ; 7 jours avant la fermeture de consultation
d’un bilan. Le calendrier figé du contrat sert au rappel en jours ouvrés.
Un bilan disponible est annoncé uniquement aux représentants dont le mandat courant
porte sur cet achat. Aucun résultat individuel détaillé ni document n’est joint.

Les délais sont configurables dans la fiche de la société exploitante par un
administrateur actif ; zéro désactive le rappel. Un nouveau rappel n’est planifié
que pour une date future. Un changement de paramètres ne rattrape pas les rappels
passés. Une prolongation rend les anciens événements obsolètes et recalcule les
échéances futures. Une action réalisée, une fin de mandat ou une correction terminée
annulent les messages devenus inutiles.

Les événements ont une clé unique par source, bénéficiaire, type et échéance.
Les reprises n’envoient pas de doublon et un conflit de création de notification
ne doit pas annuler l’action métier. Les parcours et files de correction conservent
leurs preuves propres. Le suivi planifié est borné par des curseurs afin de ne pas
laisser une page de messages anciens masquer les messages suivants.

Avant le transport natif, le compte actif, le contact, la société, la source typée,
le rôle ou mandat et l’échéance sont revérifiés. L’enveloppe doit contenir uniquement
le contact autorisé, sans copie ni pièce jointe. Les anciens messages d’activation
commerciale encore en file sont également contrôlés. Les messages renvoient vers
les espaces authentifiés ; ils ne contiennent ni question, corrigé, rendu ou motif
libre de correction. Les notifications natives de publication/achèvement eLearning
et la certification native Survey restent désactivées pour ces offres contrôlées.

Les échecs importants restent tracés et affectés à une coordination active de
l’organisme ; la relance explicite conserve le même événement. Pour les retours
humains, les règles de rejet ultérieur et de fenêtre complète de révision restent
celles de J10. Aucun test d’ouverture ou de lecture d’un courriel n’est ajouté.

Recette : vérifier les destinataires puis retirer un rôle ou mandat avant l’envoi ;
prolonger un accès ; changer un délai après passage d’un rappel ; remplacer un rendu
sans repousser son délai initial ; publier une correction ; consulter deux achats
sans détail pédagogique dans leurs courriels. Les résultats exécutés sont dans la PR.
Les invitations natives à un compte absent et la qualification du transport confiné
sont traitées dans l’incrément suivant avant la qualification finale.
