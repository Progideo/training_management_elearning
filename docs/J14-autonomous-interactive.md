# Activités interactives autonomes et historiques personnels

Suite de l’issue #19. Les leçons natives sélectionnent une version publiée de la
bibliothèque commune `training_interactive`, sans copie de fichiers par mode.
H5P TrueFalse 1.8 et SCORM 1.2 mono-SCO utilisent les mêmes lecteurs, fournisseurs,
origines isolées et autorisations courtes que TM. Le résultat reste déclaré par
le navigateur et formatif ; il ne prouve ni présence ni durée de travail.

Une obligation peut demander la terminaison ou la terminaison avec un seuil. La
version, la règle et le seuil se figent dans le plan de l’inscription native. Une
nouvelle version évaluée de la même ressource peut être choisie avec motif pour
les futurs inscrits et achats, sans modifier les plans déjà figés. Un changement
d’obligations ou de prérequis nécessite une nouvelle édition. Les libellés peuvent
être corrigés par l’action éditoriale tracée, sans changer le paquet.

Les tentatives sont propres à l’adhésion, à la leçon et au compte. Relancer reprend
la dernière tentative ; une nouvelle tentative démarre vide. Sauvegarde, événement
idempotent et projection sur `slide.slide.partner` sont atomiques. Un échec annule
l’ensemble ; un rejeu identique retrouve son reçu, un contenu divergent ou une
révision ancienne est refusé. L’acquis et sa première date ne sont pas effacés par
une performance ultérieure plus faible. Les déclarations manuelles et routes natives
ne contournent pas le critère interactif.

Les deux adaptateurs partagent le validateur borné des rapports. Leurs tentatives,
autorisations et acquis restent séparés, même pour une même personne et une même
version de fichiers. Une lecture devenue ancienne doit reprendre une transaction
actuelle ; le lancement ne crée pas de tentative concurrente en doublon.

Le lecteur et chaque accès aux fichiers revérifient le contexte, le compte, la
version, les prérequis et l’accès serveur. L’expiration ou le retrait ferme les
lectures et sauvegardes, sans effacer les acquis. Les vidéos privées sont hors
périmètre : extensions vidéo usuelles refusées à l’import, lecture média bloquée
par la politique du lecteur. Les tentatives, états et événements ne sont pas des
comptes pédagogiques concurrents du suivi natif.

Un lien « Mon historique pédagogique » rend les preuves personnelles navigables
après expiration : rendus et retours individuels autorisés, dates, scores formatifs,
scores d’examens globaux et par thème. Ce chemin ne rouvre ni support, ni état
interactif détaillé, ni question ou corrigé d’examen. Les dates sont présentées dans
le fuseau de l’utilisateur. L’ancienne assertion interdisant toute présence de
`slide.channel` dans une base TM est remplacée par l’absence de dépendance croisée,
conformément au cadrage du 3 novembre ; la séparation des acquis reste éprouvée.

## Recette

1. Ajouter une version publiée à un cours natif, choisir un critère et attribuer le
   cours. Vérifier refus de la complétion manuelle, reprise et nouvelle tentative vide.
2. Sauvegarder une réussite, rejouer l’événement puis produire un résultat inférieur :
   même reçu, pas de doublon et acquis initial conservé.
3. Changer la version pour les futurs inscrits : ancienne version et ancien seuil
   conservés pour l’inscription existante et les achats déjà confirmés.
4. Affecter le même paquet à TM et à un cours autonome : fichiers identiques,
   tentatives, autorisations et acquis distincts.
5. Expirer l’accès : lecteur et fichiers fermés, scores et rendus personnels encore
   accessibles depuis l’historique ; ni question ni corrigé dans la synthèse expirée.
6. Mettre à jour : comparer événements, états, premières acquisitions et octets des
   fichiers. Les tests réellement exécutés et la composition sont consignés dans la PR.
