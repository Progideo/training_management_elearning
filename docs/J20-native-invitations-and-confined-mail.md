# J20 — Invitations natives et transport confiné

Suite de #19, section 4 « Invitation et identité » et section 10 du cadrage.
L’inscription directe à un cours, l’activation d’un parcours et l’attribution d’un
achat autorisé préparent le compte Odoo natif du bénéficiaire lorsqu’il n’existe pas.
Les identifiants restent définis par le bénéficiaire dans le flux standard de portail.
Aucun second compte ni seconde authentification ne sont créés.

Le service interne vérifie le rôle de coordination, la société et la visibilité du
contact. Il délègue uniquement ce contact à l’assistant portail natif, sans accorder
un droit global d’administration des comptes. Un compte existant est réutilisé
uniquement s’il est unique, actif, non public et habilité dans la société. Une adresse
liée à un autre compte, même lorsque son identifiant diffère de cette adresse,
un compte inactif ou un cas ambigu nécessitent une intervention de coordination.
Aucune fusion, réactivation ou divulgation des autres relations n’est automatique.

Le message natif est placé en file et lié à l’accès accordé dans la même transaction.
Un échec de validation de l’accès annule la création du compte et de son message.
Le verrou du contact commun protège deux cours attribués simultanément ; une lecture
périmée doit être reprise. Une seconde attribution réutilise le compte et ne renvoie
pas une seconde invitation. Les sièges préparés avant autorisation commerciale ne
créent aucun accès ni invitation automatique.

Le contrôle juste avant SMTP couvre l’identité du détenteur, la société et le droit
courant. Les messages natifs d’activité ou de discussion sur les objets autonomes
sont également vérifiés : rôle courant et accès natif au dossier, sans pièce jointe
ou destinataire libre. Les notifications typées conservent leurs projections privées
pour les apprenants et représentants qui n’ont aucun accès aux preuves internes
brutes. Les objets commerciaux standards hors eLearning et les contrats des objets
historiques de bibliothèque/adaptateur TM restent distincts.

## Qualification du transport

`ci/confined_smtp.py` est un collecteur de test temporaire, sans relais, sans port
publié et sans stockage persistant. Il fonctionne uniquement sur le réseau Docker
jetable de qualification, avec l’image Odoo épinglée. Son API de reçus reste interne
à ce réseau ; aucun service supplémentaire n’est installé en production par le module.

La sonde s’exécute hors du moteur de tests Odoo, sur une base jetable imposée.
Elle utilise le transport SMTP natif réel et des adresses fictives `.invalid` :

- invitation native reçue, contenant le lien standard de définition des identifiants ;
- désactivation du compte avant envoi : aucun message reçu ;
- rejet SMTP 550 contrôlé : incident conservé, accès maintenu, puis reprise du même
  événement vers l’adresse fictive corrigée ;
- retour de TP réellement envoyé : départ de la fenêtre contractuelle complète et
  planification du rappel de révision, sans consigne, appréciation, rendu ni pièce jointe.

Le contenu est vérifié après décodage MIME. La transaction de qualification est
annulée et le collecteur supprimé. Ce test ne démontre ni la réception en boîte
principale ni le traitement réel d’une notification de rejet asynchrone ; ce dernier
état reste éprouvé séparément par les tests des retours humains.

Une seconde sonde utilise trois transactions sur deux cours et le même contact,
puis vérifie compte unique, deux accès, invitation unique et conservation après mise
à jour. Les anciens tests d’attente de compte absent sont amendés explicitement
pour D16 ; le nouveau cas ambigu conserve l’attente et l’activité de coordination.

Recette : attribuer un bénéficiaire absent ; ouvrir le parcours natif de définition
des identifiants ; répéter l’attribution ; utiliser une adresse d’un autre compte ;
vérifier la réservation sans détail d’identité ; invalider l’accès avant envoi ;
contrôler le retour de TP et sa fenêtre. Les résultats exécutés figurent dans la PR.
