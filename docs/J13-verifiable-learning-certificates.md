# Attestations eLearning vérifiables

Suite de l’issue #19 et de la section 9 du cadrage du 3 novembre. Le flux est natif
Odoo, indépendant de TM et de Ventes/Survey. La coordination pédagogique délivre
manuellement le document après acquisition des obligations du cours ou du parcours.
Le refus du titulaire ne bloque jamais cet achèvement et aucun score ou achat ne
provoque à lui seul une délivrance.

Le titulaire prévisualise son nom et l’intitulé exacts, puis accepte explicitement
l’enregistrement et la visibilité par lien. Décision, date et informations acceptées
sont conservées. Une identité modifiée avant délivrance exige une nouvelle
prévisualisation ; un refus peut être suivi d’une nouvelle acceptation. Le document
précise qu’il atteste l’achèvement pédagogique et ne prouve ni présence, ni temps
passé, ni certification officielle ou Qualiopi.

Le moteur PDF exact d’Odoo 20 produit un fichier conservé à l’identique, son empreinte
SHA-256 et un QR code contenant un lien aléatoire non prévisible. La page publique
ne présente que nom, intitulé et statut. Elle ne propose ni recherche, annuaire,
PDF, score, réponse, coordonnées ou détail pédagogique. Elle refuse l’indexation et
la mise en cache. Le téléchargement passe par une route privée contrôlant le
compte titulaire d’origine ou la coordination habilitée ; les routes natives de
fichier, les jetons et le rendu de rapport ne permettent pas de contourner ce flux.

Le retrait exige un motif interne et reste visible comme statut si la vérification
publique est autorisée. Un remplacement utilise une nouvelle acceptation, un nouveau
fichier et un nouvel identifiant ; l’ancien reste marqué remplacé, sans redirection.
La désactivation publique, par le titulaire ou la coordination avec motif, affiche
« Vérification indisponible » sans nom ni intitulé et ne retire pas la validité.
La réactivation exige une nouvelle acceptation du titulaire et un document encore
valide. Les copies déjà téléchargées ne peuvent pas être rappelées.

L’historique personnel conserve documents et décisions après expiration. Aucun PDF
ou lien n’est partagé automatiquement avec l’entreprise. Les notifications natives
renvoient seulement vers l’espace authentifié, sans pièce jointe ni lien public.
Le destinataire et son rattachement au compte d’origine sont revérifiés avant
transport. Les incidents disposent d’une reprise native ; le suivi ne se clôt qu’à
confirmation de l’état envoyé. Les tests représentent cette confirmation par une
transition native confinée, sans livraison SMTP réelle.

Les délivrances et remplacements sont atomiques. Les verrous et une révision
technique sur l’inscription canonique obligent une transaction devenue ancienne à
repartir d’un état actuel. Ce mécanisme ne modifie ni acquis, ni obligations, ni
dates pédagogiques. Les consentements, changements de statut et octets PDF restent
conservés lors des mises à jour, sans antidater d’historique.

## Recette

1. Refuser une demande, terminer le cours, constater l’absence de délivrance
   automatique ; accepter une nouvelle prévisualisation puis délivrer manuellement.
2. Télécharger le PDF avec le titulaire, vérifier nom, intitulé, référence et lien/QR ;
   refuser son téléchargement avec un autre compte ou une société étrangère.
3. Désactiver la vérification : aucune identité publique ; réactiver avec nouvelle
   acceptation puis retirer avec motif, sans changer les octets du PDF.
4. Corriger l’identité, obtenir une nouvelle acceptation et remplacer : ancien lien
   marqué remplacé, nouvel identifiant distinct et aucune redirection.
5. Répéter et concurrencer les actions ; une reprise retrouve le document délivré.
   Mettre à jour et comparer consentements, statuts, réglages publics et empreintes.

Les résultats réellement exécutés figurent dans la PR. Un exemple natif comportant
un nom et un intitulé longs a été rendu et inspecté visuellement sur une page A4,
sans débordement. La recette navigateur intégrée reste prévue après qualification
complète et déploiement de tout le périmètre.
