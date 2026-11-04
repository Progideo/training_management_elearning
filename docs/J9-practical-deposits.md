# TP déclaratifs et dépôts privés

Suite du [retrait motivé](J8-availability-notices.md), cadrage du 3 novembre,
sections 5 à 7 et 13 ; suivi GitHub #19. Cette tranche livre les critères
« autoévaluation » et « dépôt simple ». La correction humaine, son affectation,
son calendrier et la révision après expiration constituent la tranche suivante.

Le TP est une activité native du cours, avec une définition versionnée rattachée
au catalogue commun. Une définition publiée est immuable. Le changement motivé
de version conserve la famille et le critère ; les plans des adhésions et ventes
déjà confirmées gardent leur version. Changer les obligations exige une édition.
La consigne est textuelle ; les supports pédagogiques privés restent dans le cours.

La déclaration explicite ou le dépôt recevable projette la complétion sur la ligne
native, sans second pourcentage. Un dépôt n’atteste pas la qualité du travail.
L’accès, les prérequis, la version et les limites sont vérifiés côté serveur ; le
verrou d’adhésion et la clé de formulaire rendent le renvoi idempotent. Chaque
nouveau rendu recevable reste conservé, avec date serveur et empreintes des octets.
La progression acquise n’est pas annulée par un rendu ultérieur.

Les plafonds initiaux sont 5 fichiers, 20 Mio par fichier et 50 Mio par rendu.
L’administrateur configure les plafonds de l’organisme ; l’auteur les réduit par
version. La limite technique est 100 fichiers et 100 Mio au total ; les conditions
publiées restent figées. Formats initiaux : PDF, PNG, JPEG, DOCX, XLSX, PPTX, TXT,
CSV. Les formats supplémentaires reconnus sont explicités dans le paramétrage.
Le contrôle borné vérifie le format, refuse chiffrement, macros, objets actifs
bureautiques et décompression excessive. Il n’exécute aucun fichier et ne promet
ni antivirus, ni conversion, ni prévisualisation bureautique.

Le reçu de suivi est distinct des fichiers privés. Le rôle commercial ou auteur
ne donne pas accès aux rendus ; la coordination pédagogique habilitée y accède
dans ses sociétés actives. L’apprenant consulte ses propres rendus, même après
expiration normale, par une route privée dédiée. Jetons et indicateurs publics
natifs ne contournent pas ces contrôles. Suspendre/révoquer un accès reste distinct
de son expiration normale. Les nouveaux compteurs natifs sont ajoutés sans
recalcul global des statistiques et dates historiques.

## Recette courte

1. Publier deux TP (déclaration et dépôt), les inclure dans un cours et l’activer.
   Vérifier que seul le geste explicite ou le dépôt conforme progresse le cours.
2. Refuser un faux PDF, une macro, un fichier trop gros et une remise sans CSRF ;
   aucun reçu partiel ni acquis ne doit apparaître.
3. Répéter puis concurrencer la même remise : un reçu, mêmes octets et même date.
   Une nouvelle clé conserve un rendu distinct sans effacer l’acquis.
4. Changer de version explicitement : l’adhésion antérieure conserve sa consigne.
5. Tester apprenant voisin, auteur, commercial et coordination pédagogique, avec
   URL native munie d’un jeton. Après expiration, seul l’historique personnel reste
   ouvert. Mettre à jour et comparer reçus, plans, audit et empreintes des fichiers.

Résultats réellement exécutés et limites de qualification dans la PR associée.
