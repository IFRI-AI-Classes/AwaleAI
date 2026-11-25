# Diagnostic des sessions, avant correction

Analyse du code local au 25 novembre 2026. Aucun accès à la production effectué.

1. `/api/game/start` crée un UUID v4 avec `uuid4()`. Chaque démarrage crée un nouvel objet `Game`. Aucun identifiant de partie globale ni recours à la dernière partie créée.
2. Le frontend conserve le `game_id` dans `AwaleGame.gameState`. Les appels humains et IA transmettent ce champ ainsi que `version`, qui correspond aux demi-coups joués.
3. Les endpoints exigent un UUID et une version entière. Les lectures recherchent explicitement cet UUID ; les identifiants absents ou invalides ne désignent aucune partie par défaut.
4. Le serveur actif conserve plateau, scores bruts, tour et historique des positions dans `Session.game`, et noms et types dans `Session.players`. Agent et profondeur restent dans le navigateur et les requêtes IA. L'historique chronologique affiché reste dans le navigateur.
5. Le dictionnaire global `_sessions` appartient à un seul processus. Ses objets `Game` et leurs plateaux sont distincts. La table Q-Learning globale sert uniquement de modèle consulté en inférence, elle ne contient pas les sessions et ne reçoit aucune mise à jour pendant les parties web. Les recherches Minimax et Alpha-Bêta ont leurs propres états.
6. Le navigateur ne stocke pas les parties dans des cookies, `localStorage` ou `sessionStorage`. `window.awaleGame` est propre à chaque page. Les caches de coordonnées de graines ne contiennent pas de données de partie.
7. Le verrou par partie empêche les coups simultanés dans un processus. Le frontend annule les requêtes lors d'un nouveau démarrage et vérifie une génération après les attentes. Il ne vérifie cependant ni l'identifiant de la réponse ni sa version avant d'afficher un coup : une réponse mal associée peut écraser plateau, scores et joueur actif. Une ancienne réponse de la même génération peut également remplacer un état plus récent.
8. `api/session_store.py` existe, mais `api/server.py` ne l'importe pas. Aucune opération des endpoints actifs n'utilise SQLite. Le module propose déjà des transactions `BEGIN IMMEDIATE`, une sauvegarde complète et une écriture conditionnée par l'identifiant et la version. Ces mécanismes peuvent être réutilisés.
9. Plusieurs workers ont chacun un dictionnaire différent ; une partie créée par l'un est introuvable chez l'autre. Un redémarrage efface les parties. SQLite sur un fichier local commun peut coordonner des processus sur un même hôte, mais pas des instances Render avec des disques indépendants.
10. Les UUID ne sont pas réutilisés intentionnellement. En revanche, l'état associé est perdu au redémarrage et inaccessible entre workers. Le client accepte sans validation l'identifiant contenu dans une réponse de coup.

## Preuves et limites

Avant correction : 75 tests Python exécutés, 58 réussis, 17 erreurs dans `tests/test_sessions.py` car `create_app` manque. Les 8 tests JavaScript existants réussissent. Le test API existant confirme que deux parties sont isolées dans un processus ; il ne reproduit pas un mélange entre appareils.

Les défauts démontrés sont une intégration de persistance inachevée et l'absence de validation des réponses dans le navigateur. Les workers séparés expliquent la perte de sessions, pas un échange de scores entre UUID distincts. La provenance exacte des réponses observées en production exige la version réellement déployée et des traces correspondantes. Aucun élément ne permet d'attribuer ce mélange à Vercel : sur un hôte public, le frontend appelle directement l'URL Render.

## Correction retenue

Raccorder le stockage SQLite existant à tous les endpoints, supprimer le cache de parties en mémoire, conserver la vérification atomique de version lors du commit, associer chaque sauvegarde à son identifiant, et valider identifiant et progression de version côté navigateur avant et après l'animation. Les calculs IA restent hors transaction SQLite. Prévoir un disque Render persistant commun aux workers et documenter la limite des instances indépendantes.
