# Alpicturia — reprise du développement

Le dépôt contenait un prototype Python de bureau. Cette branche conserve `src/` et ajoute une première application web utilisable par les festivaliers sur téléphone, les photographes sur ordinateur et l’administration. Elle n’a pas été déployée sur un domaine public.

## Ce qui est implémenté

| Domaine | Fonctionnement disponible |
| --- | --- |
| Comptes | Inscription email et mot de passe, connexion, déconnexion, vérification email, renvoi, récupération de mot de passe, expiration des sessions et révocation après reset. |
| Permissions | Festivalier, photographe, administrateur ; aucun administrateur créé depuis une inscription publique. Un photographe doit être explicitement assigné à chaque événement. |
| Festivalier | Sélection d’événement, selfie depuis le téléphone, consentement explicite, recherche asynchrone, suivi, galerie privée d’aperçus, agrandissement, suppression d’une recherche. |
| Photographe | Import multiple et glisser-déposer, trois envois simultanés, progression, pause/reprise de la file, reprise des échecs, déduplication SHA-256 par événement et photographe, pagination et relance des indexations échouées. |
| Traitements | SQLite WAL et file persistante, transactions pour dépôt + job, lease de reprise après arrêt, détection réelle avec le moteur du prototype, index par événement, aperçus filigranés sans EXIF. |
| Administration | Comptes, événements, assignations, photos, recherches, tâches, emails, journal ; recherche et pagination ; export CSV de toutes les lignes, protection contre les formules de tableur, désactivation/réactivation de comptes, création/modification/publication d’événements. |
| Statistiques | Compteurs issus de la base, stockage original, pages vues 30 jours et historique quotidien, états des jobs et emails, configuration SMTP/IA/Search Console et heartbeat du worker. Aucun chiffre de démonstration. |
| Emails | Outbox SMTP, TLS avec validation du certificat, retries bornés, états envoyés/échoués, liens à usage unique, effacement des corps après envoi ou expiration. Aucun envoi externe effectué pendant le développement. |
| Référencement | Pages publiques et événements rendus côté serveur, titres, descriptions, canonicals, Open Graph, robots.txt et sitemap.xml dynamique. Comptes, admin, galeries et API exclus de l’indexation. Balise de vérification Search Console configurable. |
| Téléphone | CSS responsive, contrôles tactiles, capture selfie et application web installable (PWA), icônes 192/512 et page hors ligne. Aucune donnée privée mise en cache par le service worker. |
| API / MCP | API documentée via `/openapi.json`, clés personnelles hachées et révocables, expiration 90 jours, permissions read/write/admin ; 20 outils MCP via SDK officiel, stdio ou HTTP authentifié. |
| Données | Selfie supprimé après traitement même en échec, résultats expirant à 7 jours, export personnel, suppression de compte avec purge des photos et index correspondants. |
| Exploitation | Dockerfile, Compose API/worker avec volume persistant, healthcheck, commande de création admin, diagnostic, CI backend + syntaxe JS. |

## Démarrage local

Python 3.12 et un compilateur C++/CMake sont nécessaires pour dlib. L’image Docker inclut ces dépendances.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r web/requirements.txt -r web/requirements-ai.txt
cp web/.env.example .env
```

Renseigner dans `.env` : `PUBLIC_BASE_URL` (origine exacte, sans chemin), SMTP et éventuellement la vérification Google. Ne jamais committer `.env`.

Charger le fichier dans les terminaux API, worker et commande admin :

```bash
set -a
. ./.env
set +a
```

Créer le premier administrateur sans mot de passe dans l’historique du terminal :

```bash
PYTHONPATH=web python -m alpicturia.cli create-admin --email votre-email@example.com --name Baptiste
```

Lancer dans deux terminaux :

```bash
PYTHONPATH=web uvicorn alpicturia.app:app --host 127.0.0.1 --port 8000 --no-access-log
PYTHONPATH=web python -m alpicturia.worker
```

Ouvrir `/account` puis `/admin`. Créer un événement, faire inscrire un photographe et l’assigner. Le compte admin créé par l’opérateur est déjà vérifié ; les inscriptions normales exigent l’email de confirmation. Aucun code de secours public ni compte de démonstration privilégié.

## Démarrage Docker

```bash
cp web/.env.example .env
# Renseigner le domaine définitif et le SMTP dans .env.
docker compose up --build -d
docker compose exec api python -m alpicturia.cli create-admin --email votre-email@example.com --name Baptiste
docker compose exec api python -m alpicturia.cli doctor
```

Les deux services utilisent le même volume `/data`, avec le même UID non privilégié. Un worker est prévu pour le pilote ; l’architecture actuelle est une base mono-hôte, pas un stockage distribué. Docker n’était pas disponible dans l’environnement de développement : le build de l’image reste à vérifier sur l’hôte cible.

Un reverse proxy HTTPS doit précéder l’API. Conserver le port lié à `127.0.0.1`, limiter les requêtes à 25 Mo et régler les timeouts d’upload. Configurer précisément les proxys autorisés avant d’utiliser leurs en-têtes. Vérifier que `PUBLIC_BASE_URL` correspond à l’origine publique : il pilote les liens email, les cookies Secure, les canonicals et le contrôle des origines.

## Brancher le MCP

Depuis `/account`, créer une clé. Lecture : `read`. Modifications : ajouter `write`. Administration : ajouter aussi `admin` depuis un compte admin. Une clé ne peut ni créer d’autres clés ni supprimer un compte. Les droits du compte restent vérifiés à chaque requête.

Configuration d’un client MCP local (adapter les chemins absolus) :

```json
{
  "mcpServers": {
    "alpicturia": {
      "command": "/chemin/du/projet/.venv/bin/python",
      "args": ["-m", "alpicturia.mcp_server"],
      "env": {
        "PYTHONPATH": "/chemin/du/projet/web",
        "ALPICTURIA_API_URL": "http://127.0.0.1:8000",
        "ALPICTURIA_API_TOKEN": "CLE_PERSONNELLE_A_CONSERVER_LOCALEMENT"
      }
    }
  }
}
```

Le serveur HTTP se lance avec `MCP_TRANSPORT=streamable-http`, un `MCP_HOST`/`MCP_PORT` approprié et les listes exactes `MCP_ALLOWED_HOSTS` et `MCP_ALLOWED_ORIGINS`. Chaque appelant fournit sa propre clé dans `Authorization: Bearer …`. En HTTP, aucune clé opérateur partagée n’est utilisée. L’endpoint est `/mcp`. Le serveur utilise le protocole pris en charge par le SDK Python épinglé ; les clients doivent supporter ce protocole et l’authentification par clé. L’intégration directe aux clients exigeant OAuth reste à ajouter.

Les outils couvrent le compte, événements publics/assignés, upload, photos, relance/suppression, selfie avec consentement, recherches/résultats, export personnel, liste/révocation des clés, aperçu admin, tables/CSV, création/modification d’événement, assignations, activation/désactivation des comptes et relance d’emails. Les images sont transmises en base64 ; les fichiers restent soumis à la validation de l’API. Pour des milliers de photos, préférer le portail web ou l’API binaire.

## Validation

```bash
PYTHONPATH=web python -m unittest discover -s web/tests -v
node --check web/alpicturia/static/app.js
node --check web/alpicturia/static/sw.js
python -m compileall -q web/alpicturia
```

29 tests automatiques API et protocole MCP passent sans modèle IA. Un 30e test opt-in valide réellement indexation → selfie → correspondance → aperçu privé → suppression du selfie :

```bash
ALPICTURIA_FACE_TEST_IMAGE=/chemin/photo-test-avec-un-seul-visage.jpg PYTHONPATH=web python -m unittest discover -s web/tests -v
```

Le test réel a été exécuté avec une image de test déjà présente dans le dépôt. C’est une vérification du branchement du moteur sur une même image, pas une mesure de précision sur un festival. Le seuil 0.48 doit être calibré sur un jeu consenti de vraies photos d’événement. Aucune promesse de retrouver toutes les photos.

Les écrans publics et les formulaires connexion/inscription ont été inspectés dans le navigateur. Les parcours authentifiés ont été vérifiés par tests API. Les vues à très faible largeur, la caméra Samsung réelle, les installations PWA, les envois SMTP réels et les gros imports réseau doivent être éprouvés sur les appareils et l’hébergement cibles.

## Avant l’ouverture publique

1. Choisir l’hébergement et le domaine, déployer la branche, renseigner le SMTP et tester réception, rebond, expiration et reset avec une boîte de test.
2. Créer le vrai compte admin via la commande opérateur. Vérifier ses accès avec un second navigateur festivalier et un photographe assigné.
3. Vérifier le domaine dans Search Console puis soumettre `/sitemap.xml`. La génération du sitemap ne soumet pas automatiquement le site à Google et ne garantit pas son indexation.
4. Compléter les coordonnées du responsable, l’hébergement, le support, les droits des photographes/organisateurs et la conservation des photos et des index faciaux. La page de confidentialité identifie explicitement ces informations à compléter.
5. Tester avec un événement pilote consenti, y compris un échec réseau, une photo sans visage, un selfie à plusieurs visages, des comptes distincts et une suppression.
6. Mettre en place sauvegarde et restauration du volume chiffré. Pour un snapshot simple cohérent, arrêter brièvement API et worker, sauvegarder le volume complet (SQLite + fichiers), puis relancer. Tester la restauration dans un environnement isolé. Protéger les sauvegardes et définir leur purge ; la suppression dans les données actives n’efface pas une ancienne sauvegarde.

## Limites assumées et travail métier restant

- Application mobile actuelle : web responsive/PWA. Aucun binaire Android/iOS ni publication Play Store/App Store n’a été créé.
- Import repris au niveau du fichier entier ; pas de reprise multipart à l’octet. Les originaux RAW ne sont pas acceptés dans cette première web app, même si le prototype de bureau sait les convertir.
- Pour le pilote, originaux et index résident sur disque local et SQLite. S3, multipart, vecteurs indexés, workers multiples et tests de charge sont les prochains travaux de montée en charge.
- La file email fonctionne en au-moins-une-fois : un arrêt après acceptation SMTP et avant confirmation locale peut produire un doublon. Le Message-ID est stable, mais la déduplication finale dépend du fournisseur.
- Un événement dépublié cache les résultats et aperçus côté festivalier. Les photographes voient leurs propres originaux. Les festivaliers voient uniquement les aperçus candidats filigranés ; un filigrane visible ne remplace pas un contrôle de licence.
- Le paiement, la livraison d’originaux achetés, les commissions et les reversements ne sont pas implémentés. Aucun faux checkout n’est affiché.
- Pas de connexion Google/ChatGPT, d’OAuth MCP, de MFA admin ou d’application native dans cette branche. L’authentification disponible est email/mot de passe.
- Pas d’envoi de données à un service de télémétrie externe. Les mesures et journaux sont locaux.
