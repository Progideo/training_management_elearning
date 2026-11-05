# Identification du lecteur vidéo public

Référence : [EL #42](https://github.com/Progideo/training_management_elearning/issues/42).

YouTube demande un référent identifiant le site intégrateur ; sa suppression
produit l’erreur 153. Voir la [référence officielle du lecteur](https://developers.google.com/youtube/iframe_api_reference#onError)
et les [exigences d’identification](https://developers.google.com/youtube/terms/required-minimum-functionality#api-client-identity-and-credentials).

Le seul iframe d’une vidéo explicitement publique utilise `strict-origin` :
seuls protocole, hôte et port peuvent être transmis, jamais le chemin privé,
l’identifiant d’adhésion ou les paramètres. La page privée conserve sa politique
`no-referrer`, son absence de cache et les contrôles courants d’accès.
Les restrictions de l’iframe restent identiques.

Recette : ouvrir une vidéo publique autorisée, lancer la lecture, vérifier que
la progression reste déclarative et qu’un autre compte ne lit pas sa page privée.
