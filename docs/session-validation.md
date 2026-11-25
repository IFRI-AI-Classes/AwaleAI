# Rapport de correction des sessions

Validation locale du 25 novembre 2026, Python 3.13.0 et Node.js 24.3.0.

## Cause exacte du bug dans le code examiné

Le frontend accepte les réponses de coups sans vérifier qu'elles portent l'identifiant demandé et la version suivante attendue. Une réponse avec `game_id=B` reçue pendant un coup de A remplace directement `gameState`, donc aussi le plateau, les scores et le joueur actif. Huit nouveaux tests ont reproduit ces écrasements avant la correction, pour les coups humains et IA, puis ont réussi après correction.

La persistance était aussi inachevée : le module SQLite existait mais les endpoints utilisaient exclusivement le dictionnaire `_sessions` du processus. Une autre instance du serveur ne pouvait pas relire une partie, et un redémarrage la supprimait. Les 17 tests de sessions existants échouaient avant correction car `create_app` n'existait pas.

Les objets `Game`, `Board` et les recherches IA sont déjà indépendants. Aucun échange de scores entre UUID distincts n'a été reproduit dans le backend initial à un seul processus. Des workers séparés expliquent des parties introuvables, mais ne suffisent pas à expliquer un échange de scores. La provenance d'une réponse mal associée dans l'incident réel reste à confirmer avec la version déployée et des traces de production. Aucun test ni accès en production effectué ; aucune responsabilité de Vercel déduite sans preuve.

## Fichiers concernés et corrections appliquées

| Fichier | Modification et raison |
| --- | --- |
| `api/server.py` | Suppression du dictionnaire de parties en mémoire, fabrique `create_app`, stockage choisi par `AWALE_DB_PATH`, chargement SQLite pour chaque opération, sauvegarde avant réponse. Conservation des UUID v4 et des contrôles de version, tour, type, plateau et profondeur. Persistance des paramètres IA et des coups. Erreurs de stockage en HTTP 503, conflits en 409, sessions absentes en 404. Health check du stockage et réponses de partie sans cache. |
| `api/session_store.py` | Réutilisation des transactions et de l'écriture conditionnelle existantes. Chaque session restaurée porte son identifiant ; une sauvegarde sous l'identifiant d'une autre partie est refusée. Une écriture de coup doit avancer exactement d'une version. Ajout de l'historique chronologique et validation des paramètres IA sauvegardés. Les anciennes sauvegardes de schéma 1 restent lisibles. |
| `web/app.js` | Identifiant et version capturés au départ de la requête. Vérification de la génération, de l'identifiant et de la version courante après réception et après animation. Refus d'une réponse d'une autre partie ou d'une version inattendue avant animation, scores, historique et télémétrie. Démarrage exigeant un nouvel UUID v4 et la version zéro. Envoi des paramètres propres aux joueurs au démarrage. Requêtes sans cache. |
| `tests/test_api.py` | Adaptation des tests existants à des bases SQLite temporaires ; conservation des scénarios et des contrôles de sécurité. Les positions de test conservent un historique cohérent. |
| `tests/test_sessions.py` | Conservation et exécution des tests de persistance déjà présents, ajout des scénarios ci-dessous avec fichiers temporaires, clients distincts, vraies requêtes HTTP et processus séparés. |
| `tests/test_web.cjs` | Ajout de régressions sur les réponses étrangères ou obsolètes, une version plus récente pendant l'animation, les démarrages retardés et invalides, les paramètres IA et deux clients frontend indépendants. |
| `render.yaml` | Configuration proposée avec une instance, deux workers, un disque persistant et un chemin SQLite commun. |
| `vercel.json` | Frontend statique conservé ; appels API éventuels transmis au même backend Render au lieu d'une fonction Python avec un stockage séparé. |
| `pyproject.toml` | Suppression de l'ancien point d'entrée Python Vercel, seule configuration contenue dans ce fichier. |
| `.gitignore` | Exclusion des bases locales et de leurs fichiers journaux. |
| `README.md` | Architecture, fonctionnement, configuration de déploiement, limites et résultats des tests actualisés. |
| `docs/session-diagnosis.md` | Diagnostic consigné avant toute modification fonctionnelle. |
| `docs/session-validation.md` | Présent rapport et correspondance entre scénarios demandés et tests exécutés. |

Les règles, Minimax, Alpha-Bêta et Q-Learning sont conservés. Aucun entraînement n'est effectué pendant une partie web, aucun taux de victoire d'entraînement n'est ajouté. Les identifiants `player1` et `player2` restent les rôles de l'API, toujours associés à un `game_id` précis. Le contrat des réponses existantes est conservé.

## Concurrence et cohérence

Chaque lecture reconstruit un nouvel état depuis SQLite, sans cache de plateau. Les verrous par partie réduisent les conflits dans un processus. L'isolation entre processus repose sur SQLite : après lecture et validation, l'écriture utilise `WHERE game_id = ? AND version = ?` dans une transaction `BEGIN IMMEDIATE`. Si une autre requête a déjà enregistré le coup, la version ne correspond plus et HTTP 409 est renvoyé. Aucun état calculé sur une ancienne version n'est enregistré.

Le calcul IA se déroule sur un état privé hors transaction de base de données ; les autres parties peuvent continuer. Plateau, scores, joueurs, paramètres IA, tour, historique des positions et coups sont enregistrés ensemble. Une erreur pendant l'écriture ou le commit annule la transaction et produit HTTP 503, sans retour d'un plateau avancé ou d'une télémétrie de succès.

## Tests effectués

| Scénario demandé | Vérification exécutée | Résultat |
| --- | --- | --- |
| 1. Deux parties indépendantes | Plusieurs coups alternés sur A et B, comparaison à deux moteurs indépendants et à leurs sauvegardes complètes. | Réussi |
| 2. Parties simultanées | Cent parties créées et jouées par dix threads sur quatre applications partageant SQLite ; contrôle individuel des états après redémarrage. Deux parties jouent aussi simultanément par HTTP réel vers un processus Uvicorn séparé. | Réussi |
| 3. Scores isolés | Captures réelles à partir du plateau initial dans A, puis B. À chaque coup, l'autre plateau et ses scores restent identiques. | Réussi |
| 4. Joueurs isolés | Noms distincts, rôles associés au bon UUID, tours indépendants, paramètres Minimax et Alpha-Bêta conservés séparément après redémarrage. | Réussi |
| 5. Requêtes concurrentes | Doublons humains et IA entre applications ; deux processus forcés à charger et valider la même version avant sauvegarde. Un HTTP 200, un HTTP 409, une seule version et un seul coup enregistrés. Calcul IA bloqué sans bloquer une autre partie. | Réussi |
| 6. Persistance | Restauration de cent parties, continuation dans un nouveau processus, scores bruts et fin par capture, blocage, répétition ou limite conservés. Compatibilité des anciennes sauvegardes de schéma 1. | Réussi |
| 7. Requêtes invalides et obsolètes | UUID absents, invalides ou inconnus, versions anciennes et futures, mauvais tour ou type, coup invalide, UUID dupliqué et sauvegarde croisée refusés. Échecs SQLite, commit, stockage verrouillé et sauvegardes corrompues contrôlés. | Réussi |
| 8. Plusieurs clients | Clients HTTP avec cookies différents, réponses sans `Set-Cookie` ni cache ; deux environnements frontend indépendants. Réponses HTTP étrangères ou anciennes rejetées, aucune restauration après arrêt ou nouveau démarrage. | Réussi |

Commandes exécutées après correction :

```text
python -B -X utf8 -m unittest discover -s tests -v
node --test tests/test_web.cjs
node --check web/app.js
git diff --check
```

Résultat après la dernière revue : **85 tests Python réussis et 29 tests JavaScript réussis**, sans échec. Les 58 tests Python hors sessions et les 8 scénarios JavaScript initiaux restent couverts. Syntaxe JavaScript et différences Git vérifiées. `vercel.json` et `render.yaml` ont été analysés localement comme JSON et YAML ; l'adresse du proxy correspond à celle de `web/app.js`. Cette validation ne constitue pas une validation des plateformes distantes.

## Risques restants

- SQLite exige que les workers utilisent le même fichier local. Des instances avec des disques indépendants n'ont pas de persistance commune. La configuration fournie fixe une seule instance Render.
- Cent parties ont été testées localement, avec des recherches IA de profondeur limitée. Cela ne mesure ni les latences ni la capacité CPU de Render pour cent recherches profondes simultanées. Un verrou SQLite dépassant le délai existant de cinq secondes renvoie HTTP 503 et ne mélange pas les parties.
- Le TTL d'une heure et la limite de 256 parties actives sont conservés. Les anciennes parties uniquement en mémoire seront perdues lors du premier déploiement.
- La reprise automatique après rechargement de la page reste absente, comme avant la correction. La persistance backend et la lecture explicite par identifiant sont validées.
- La cause de production qui aurait acheminé une réponse incorrecte vers le navigateur n'a pas été observée. Il reste nécessaire de vérifier la version réellement déployée et les traces si l'incident se reproduit.

## Déploiement

Appliquer au service Render existant les paramètres du fichier `render.yaml` : disque persistant `/var/data`, `AWALE_DB_PATH=/var/data/awale/sessions.sqlite3`, une instance, workers ouvrant ce fichier. L'offre Render doit prendre en charge les disques persistants, le modèle fourni utilise `starter`. Le schéma SQLite est créé automatiquement. Une sauvegarde existante de schéma 1 n'est pas réinitialisée.

Déployer aussi le frontend corrigé et `vercel.json` pour appliquer les contrôles de réponses et faire passer les appels API Vercel vers Render. Le frontend public conserve son appel direct à Render. Si l'adresse du service diffère, ajuster ensemble `web/app.js` et `vercel.json`.

Aucune nouvelle dépendance de production requise : SQLite appartient à Python. `httpx` est déjà déclaré dans `requirements-dev.txt` pour les tests. Aucun service distant, variable d'environnement de production ou compte Render/Vercel n'a été modifié pendant cette intervention.

## Dernière revue technique avant commit et déploiement

Le diff Git complet des fichiers suivis, les fichiers encore non suivis et le présent rapport ont été examinés. Aucun commit ni déploiement effectué.

### Défaut découvert et corrigé

Le backend refuse correctement une ancienne version avec HTTP 409, mais le frontend affichait seulement une erreur et conservait cette version. Après un coup déjà enregistré par un autre client ou une réponse perdue, les tentatives suivantes pouvaient donc rester refusées indéfiniment.

Deux tests, humain et IA, ont reproduit l'absence de relecture avant correction. `web/app.js` relit maintenant `/api/game/{game_id}` après HTTP 409, sans cache. La réponse est appliquée seulement si son identifiant correspond, si sa version ne régresse pas et si la génération et l'état attendu sont toujours courants. Le prochain coup utilise la nouvelle version. Le tour IA reprend automatiquement si nécessaire. Un arrêt ou une nouvelle partie annule cette actualisation et son tour programmé.

Neuf tests JavaScript supplémentaires couvrent cette correction, la requête suivante, les réponses étrangères, anciennes ou en erreur, les actualisations retardées et les tours IA annulés. Les 85 tests Python et 29 tests JavaScript ont tous été relancés et réussissent. Seuls le frontend, ses tests et la documentation ont été modifiés pendant cette revue.

### SQLite

- `AWALE_DB_PATH` est lu à la création de l'application et le chemin est résolu. `/var/data/awale/sessions.sqlite3` est bien sous le montage `/var/data`. Chaque ouverture exécute `mkdir(parents=True, exist_ok=True)` sur le répertoire parent. La création d'un fichier dans des répertoires imbriqués initialement absents a été vérifiée localement ; le montage Render réel n'a pas été inspecté.
- Mesures sur une connexion créée par le stockage : `journal_mode=delete`, `synchronous=2` (FULL), `busy_timeout=5000` millisecondes. `sqlite3.connect(timeout=5.0)` configure déjà ce délai sur chaque connexion.
- Le journal de rollback, `BEGIN IMMEDIATE` et la sauvegarde conditionnée par la version sont compatibles avec deux processus sur le même disque local. WAL n'est pas nécessaire à la correction : même les lectures qui renouvellent le TTL sont de courtes transactions d'écriture. WAL pourrait être étudié pour la performance si une contention réelle le justifie, mais il ne permettrait toujours qu'un écrivain à la fois.
- Une erreur SQLite, y compris SQLITE_BUSY après expiration du délai, est convertie en HTTP 503. Les erreurs de commit et les écritures partiellement exécutées sont testées avec rollback. Pas de retry automatique du coup et pas de cache de partie avancée en mémoire.
- Tous les démarrages et coups passent par SQLite avant leur réponse de succès. Les objets en mémoire sont uniquement des états privés de requête et des verrous, pas une persistance alternative.

### Render et Vercel

Le Blueprint correspond à la documentation Render : service Python `starter`, disque de 1 Go monté sur `/var/data`, une instance, deux workers Uvicorn et health check `/`. Aucun `--reload`, `scaling`, migration pendant le build ou chemin de stockage contradictoire dans le fichier. Pour un service existant, vérifier néanmoins dans le tableau de bord que l'autoscaling est désactivé : Render peut conserver d'anciens réglages, et `numInstances` ne s'applique pas à un service autoscalé. Un disque attaché impose une seule instance.

Le disque est disponible uniquement à l'exécution, pas pendant le build ou une commande de pré-déploiement. Son ajout déclenche un redéploiement ; les redéploiements avec disque provoquent une courte interruption pendant le remplacement de l'instance. Ces contraintes sont à prévoir lors de l'application manuelle des paramètres.

Les routes Vercel historiques `routes` et `builds` restent prises en charge. L'URL externe dans `dest` est un usage documenté. Le builder statique inclut les fichiers `web/**`, et la substitution `/api/game/...` transmet bien `/api/game/...` à Render. Le frontend public continue d'appeler Render directement et le CORS autorise cet appel. La suppression de `pyproject.toml` retire uniquement deux lignes de configuration Vercel ; aucun paquet Python ni métadonnée de projet n'y était défini. `requirements.txt` reste le fichier utilisé sur Render.

### Étapes exactes de déploiement manuel

1. Terminer la revue et préparer le commit incluant aussi les fichiers actuellement non suivis : `api/session_store.py`, `tests/test_sessions.py`, `render.yaml` et les rapports `docs/`. Ne pas inclure les bases SQLite locales. Vérifier les réglages de déploiement automatique avant de pousser une branche de production ; choisir une branche de prévisualisation pour valider Vercel avant promotion.
2. Dans le service Render existant, vérifier le dépôt et sa racine, choisir le runtime Python et une offre compatible avec disque persistant. Désactiver l'autoscaling et conserver une seule instance. Désactiver Auto-Deploy si le déploiement doit rester entièrement manuel.
3. Dans Environment, définir impérativement `AWALE_DB_PATH=/var/data/awale/sessions.sqlite3`. Fixer aussi une version Python complète avec `PYTHON_VERSION` pour éviter de dépendre de l'ancienneté du service. La validation locale a utilisé `3.13.0` ; une autre version, notamment une version maintenue plus récente, doit être revalidée. Ne pas configurer manuellement `PORT`, fourni par Render.
4. Dans Disks, ajouter ou conserver le disque `awale-sessions`, montage `/var/data`, capacité de 1 Go. Si un disque existe déjà avec une base à préserver, sauvegarder cette base avec l'API de sauvegarde SQLite et vérifier son chemin avant tout changement de montage. L'ajout du disque déclenche un redéploiement du service.
5. Configurer Build Command : `pip install -r requirements.txt`. Configurer Start Command : `uvicorn api.server:app --host 0.0.0.0 --port $PORT --workers 2`. Health Check Path : `/`. Déployer manuellement le commit validé une fois les paramètres prêts. Aucune migration manuelle ni commande de pré-déploiement : le schéma est créé au démarrage effectif ou à la première requête. Les anciennes sauvegardes de schéma 1 sont compatibles.
6. Après déploiement Render, vérifier HTTP 200 sur `/`, la création de `/var/data/awale/sessions.sqlite3` et les deux workers dans les journaux. Créer deux parties de contrôle, jouer dans chacune, relire les deux UUID, puis effectuer un redémarrage contrôlé et vérifier leur restauration. Un succès de build seul ne vérifie pas la persistance.
7. Dans Vercel, conserver la racine du dépôt, preset Other et la configuration `vercel.json`. Le projet ne nécessite aucune variable d'environnement Vercel, aucun installateur Python ni commande de build applicative. Avec `builds`, les artefacts statiques viennent du builder explicitement configuré ; ne pas remplacer cette configuration par une détection FastAPI ou une racine `web` qui ignorerait `vercel.json`.
8. Déployer d'abord une prévisualisation Vercel du commit. Vérifier `/`, `/index.html`, `/app.js`, `/styles.css`, le démarrage d'une partie et `/api/agents` via le proxy. Confirmer que les requêtes de jeu publiques utilisent l'URL Render attendue. Si le nom de domaine Render réel diffère, mettre à jour ensemble `web/app.js` et `vercel.json`, puis revalider avant promotion.
9. Promouvoir manuellement la prévisualisation validée en production. Vérifier avec deux navigateurs ou appareils que leurs UUID et états restent distincts. Aucun de ces contrôles distants n'a été effectué pendant cette revue.

Les dépendances de production nécessaires sont toutes déclarées : FastAPI, Uvicorn et Pydantic ; les autres imports du backend sont internes ou appartiennent à Python. Versions locales testées : FastAPI 0.139.0, Uvicorn 0.51.0, Pydantic 2.12.5, httpx 0.28.1 et SQLite 3.45.3. Les contraintes `>=` ne figent pas les futures installations ; comparer les versions installées lors du build à l'environnement validé. Aucun défaut de dépendance démontré et aucune modification de dépendance effectuée.

### Problèmes restants

Aucun autre défaut bloquant identifié dans les modifications examinées. La configuration réelle des comptes, le montage du disque, la résolution du domaine Render et la réponse de la prévisualisation Vercel restent à vérifier manuellement. Les limites de charge, de TTL et de reprise après rechargement décrites plus haut sont conservées. Après resynchronisation, l'historique affiché conserve les coups déjà connus du navigateur, sans inventer les coups effectués ailleurs ; la sauvegarde SQLite conserve l'historique complet de la partie.

Références consultées : [Blueprint Render](https://render.com/docs/blueprint-spec), [disques persistants Render](https://render.com/docs/disks), [version Python Render](https://render.com/docs/python-version), [configuration Vercel](https://vercel.com/docs/project-configuration/vercel-json) et [journal WAL SQLite](https://www.sqlite.org/wal.html).
