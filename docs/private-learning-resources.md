# Ressources complémentaires privées

`training_elearning_resources` est un complément optionnel LGPL-3 pour Odoo 20
Community, dépendant seulement de `training_elearning`. Il ne modifie aucun fichier
de ce dernier ni le cœur d’Odoo. Il ajoute une extension ORM et des vues héritées.
L’application conserve ses comptes, cours, adhésions et échéances existants.

## Usage

1. Installer le complément sur une composition qualifiée, avant d’attribuer les
   nouvelles éditions de cours.
2. Comme auteur, ouvrir une activité du formulaire **Cours autonomes**, puis
   **Ressources complémentaires**. Ajouter un fichier ou une URL HTTP(S).
3. Publier l’édition puis attribuer l’accès par l’action native existante.
4. L’apprenant retrouve les ressources regroupées par activité sur la page de son
   cours. Les prérequis et indisponibilités de l’activité restent applicables.

Formats téléchargeables : ZIP, XLSX, XLS, PNG, GIF, JPG/JPEG ; les PDF natifs sont
également conservés. Maximum : **64 Mio par fichier**, non vide, nom sans chemin.
Les images et classeurs sont téléchargés dans leur format d’origine : le module
n’ajoute pas de lecteur Excel ni de prévisualisation d’images. Les animations GIF
restent dans le fichier original. Le redimensionnement natif des grandes images
est désactivé uniquement pour ces ressources ; il reste inchangé ailleurs. Un ZIP est un fichier à télécharger, sans
extraction ni exécution comme SCORM/H5P. Les vérifications portent sur le format
apparent/conteneur, sans analyse antivirus ni certification du contenu d’un classeur.
Les fichiers Excel avec extension XLSM et les images SVG ne sont pas admis.

Les URL doivent être absolues, sans identifiants ni espaces. Le clic passe par le
contrôle d’accès puis une redirection vers le site externe. Aucun contenu distant
n’est téléchargé par le serveur ou intégré dans une iframe. Le site externe reste
responsable de son propre accès : l’expiration du cours ferme le lien du portail,
mais ne peut pas retirer une URL externe ou un fichier déjà mémorisé/téléchargé.

## Autorisations et immutabilité

Le stockage est celui de `slide.slide.resource` et des pièces jointes natives.
Aucun nouveau référentiel d’apprenants, modèle de progression, groupe ou service
externe n’est ajouté. Les auteurs utilisent les droits natifs et la société active.
Les apprenants passent exclusivement par la route authentifiée du complément.

À chaque téléchargement/redirection : réutilisation de `_activity` pour vérifier
le compte actif désigné par l’adhésion, les sociétés autorisées du compte, l’état
et l’échéance de l’accès, le cours, l’activité et ses prérequis. Pour un TP, le
contrôle pratique existant est également appelé ; aucune exception de correction
tardive ne prolonge l’accès aux ressources. L’ID demandé doit appartenir au plan
figé et à cette activité. Métadonnées, taille et SHA-256 du fichier sont revérifiés.
Les ressources ne modifient ni la progression ni les critères de complétion.

Les plans capturent les ressources au même point de gel que les autres contenus.
Après attribution/vente engageant l’édition, création, modification, déplacement,
suppression des ressources et modification de leurs pièces jointes sont refusés.
Créer une nouvelle édition pour changer une ressource. Verrouillage du même graphe
de cours que l’activation et mise à jour du parent empêchent une transaction
concurrente de figer un ancien instantané après une modification des ressources.

Les accès RPC ordinaires, `/web/content`, `/web/image` et les anciens jetons de
pièces jointes ne servent pas ces fichiers aux apprenants ou au public. Les cours
Community non gérés gardent leur fonctionnement natif. Les fichiers sont servis
en téléchargement avec `no-store`, `nosniff`, `no-referrer` et une CSP restrictive.
Le module doit rester installé tant que ces ressources sont utilisées.

Les plans déjà figés avant installation ne sont **pas réécrits**. Ils n’acquièrent
pas automatiquement de nouvelles ressources : préparer une nouvelle édition et
attribuer explicitement ses droits. Aucun accès ou courriel n’est créé à
l’installation. La migration métier reste dans le dépôt d’exploitation.

## Qualification manuelle reproductible

Image Odoo épinglée dans `bench/compose.yaml` :
`odoo@sha256:61e3c71b0503c5f658e604c3e340bede20b97d05f726179fa006eae50a32fd23`.
Dépendances partagées issues du commit TM
`645dfe160f5d413684b00f56daabe1fcaa59c4d6` ; base eLearning
`98f112757f918000e9a1923d671005b5a03cf3c9` (pile de PR, pas de fusion implicite).

Exécuter depuis ce dépôt, avec Docker et les images déjà disponibles :

```sh
python3 bench/test-resources.py \
  --shared-addons /chemin/vers/composition-qualifiee/addons \
  --output /private/tmp/learning-resources-qualification
```

Le dossier de sortie doit être nouveau. Le banc crée uniquement une base fictive
locale, un réseau Docker interne, aucun port publié, aucun cron et aucun serveur
SMTP utilisable. Il teste installation, droits et HTTP natif ; garde ensuite une
édition attribuée pour vérifier la mise à jour sans changement des droits, plans,
progression ou octets ; vérifie deux transactions PostgreSQL concurrentes, puis
restaure la base et le filestore et répète les contrôles. Les régressions existantes
des leçons, du portail et des indisponibilités sont également sélectionnées.
Ajouter `--full-composition` pour installer aussi les applications TM, Ventes et
Examens de la composition épinglée et répéter leurs tests concernés.
Les journaux et la sauvegarde fictive restent dans la sortie locale ; ne pas
utiliser ce banc contre une base réelle. Il n’appelle aucune CI.

Résultats effectivement obtenus : voir la preuve associée à cette PR.
