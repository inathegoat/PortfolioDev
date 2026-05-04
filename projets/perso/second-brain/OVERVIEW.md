# Overview — Second Brain

## Résumé du Projet

**Second Brain** est un système d'intelligence artificielle personnel, localement installé, qui fonctionne comme un « second cerveau » pour l'utilisateur. Le système permet d'ingérer des documents personnels (PDF, TXT, Markdown), de poser des questions via une interface conversationnelle, et de recevoir des réponses intelligentes basées sur le contenu des documents. Contrairement aux assistants IA classiques qui envoient les données vers le cloud, Second Brain conserve toutes les informations sur la machine locale, garantissant une confidentialité totale sans appels API externes ni traçage.

Le projet a évolué au-delà d'un simple système de questions-réponses pour devenir une architecture multi-agents complète capable d'analyse stratégique, de planification, d'exécution de tâches et d notifications proactives. Cette plateforme s'apparente à un « Jarvis » personnel qui analyse automatiquement les interactions passées, détecte les schémas importants, génère des tâches pertinentes et rappele à l'utilisateur les actions à effectuer.

## Architecture Générale

L'architecture de Second Brain suit un flux de données en couches distinctes. La **Data Layer** gère les fichiers sources (PDF, TXT, MD) et le stockage SQLite pour les métadonnées. La **Processing Layer** assure le parsing des documents, le chunking du texte et la génération des embeddings. La **Memory Layer** maintient l'index vectoriel ChromaDB et l'historique des conversations. finalement, la **AI Layer** orchestre le pipeline RAG et les模型的 d 语言 via Ollama.

Cette organisation modulaire permet à chaque composant de fonctionner indépendamment tout en s'intégrant dans un pipeline cohérent : ingestion des documents → stockage → retrieval → génération de réponse.

## Structure des Répertoires

### Racine du Projet

Le répertoire principal contient les fichiers essentiels au fonctionnement du système. À la racine se trouve `main.py`, le point d'entrée CLI qui expose toutes les commandes disponibles (ingest, query, chat, agent, goals, tasks, tools, dashboard, telegram). On y trouve également `README.md` avec la documentation originale, `requirements.txt` listant les dépendances Python, et `.env` pour les variables d'environnement (clés API, paramètres de configuration). Le dossier `config/` contient `settings.py`, le fichier centralisé de configuration qui définit tous les chemins, modèles et paramètres système.

### `src/` — Code Source Principal

Le répertoire src/ contains le code cœur du système, organization en plusieurs modules fonctionnels.

#### `src/agent/` — Système Multi-Agents

Le dossier agent/ implémente l'architecture multi-agents sophistication qui constitue le « cerveau » actif du système. Le fichier `coordinator.py` orchest le flux entre les six agents spécialisés, gère le partage des données et maintient l'état entre les cycles. L'agent adaptatif (adaptive_agent.py) évalue ce qui s'est passé depuis le dernier cycle et détecte les ajustements nécessaires. L'agent stratégique (strategic_agent.py) analyse la situation courante, identifie les opportunités et menaces, et évalue l'état actuel des objectifs.

L'agent planner (planner_agent.py) crée une feuille de route concrète avec des jalons et des délais. L'agent critique (critic_agent.py) identifie les risques, les étapes irréalistes et les dépendances manquantes. L'agent optimizer (optimizer_agent.py) affine le plan en tenant compte des critiques pour produire un plan d'exécution optimisé. L'agent executor (execution_agent.py) sélectionne la tâche principale immédiate et les tâches secondaires à effectuer.

Le fichier `brain_loop.py` implémente la boucle proactive « Jarvis Mode » qui fonctionne en arrière-plan, analyze les mémoires, génère des insights et envoie des rappels. Le fichier `insights.py` génère des insights actionnables à partir des memorized importance via le LLM local. Le fichier `task_generator.py` convertit les insights en tâches structurées liées aux objectifs. Le fichier `attention.py` gère le système d'attention qui priorise les memorized en fonction des objectifs. Les fichiers `notifier.py` et `follow_up.py` gèrent les notifications bureau et le suivi des rappels.

#### `src/ai/` — Pipeline RAG et Client LLM

Le dossier ai/ contient les composants d'intelligence artificielle. Le fichier `llm_client.py`-interface avec Ollama (ou autre provider compatible OpenAI), génèrant du texte à partir de prompts. Le fichier `rag_pipeline.py` implémente le pipeline Retrieval-Augmented Generation complet : embedding de la question, retrieval dans ChromaDB, nettoyage et reranking des résultats, construction du prompt enrichi (mémoire + contexte + question), génération de la réponse via le LLM, et sauvegarde automatique dans l'historique.

#### `src/memory/` — Stockage et Historique

Le dossier memory/ gère la persistance des données. Le fichier `vector_store.py`-interface avec ChromaDB pour le stockage et le retrieval vectoriel. Le fichier `history.py` maintient l'historique des interactions Q&A en JSON, permet l'injection dans les prompts pour la continuité conversationnelle. Le fichier `conversation.py` fournit des utilitaires pour formater l'historique.

#### `src/data_layer/` — Gestion des Documents

Le fichier `document_manager.py` gère le cycle de vie complet des documents : scan du répertoire raw, registration dans la base SQLite avec hash de déduplication, parsing, mise à jour du statut.

#### `src/processing/` — Prétraitement des Données

Le dossier processing/ prépare les données pour l'embedding. Le fichier `parsers.py` parse les PDF (via PyMuPDF), TXT, Markdown et autres formats. Le fichier `chunker.py` segmente le texte en chunks avec overlap pour maintenir le contexte. Le fichier `embedder.py` génère les embeddings textuels via sentence-transformers.

#### `src/tools/` — Système d'Outils

Le dossier tools/ implémente un système d'outils extensible pour exécuter des actions concrètes. Le fichier `base.py` définit la classe de base Tool. Le fichier `registry.py` enregistre et liste les outils disponibles. Le fichier `builtin.py` implémente les outils intégrés (recherche web, exécuter du code). Le fichier `llm_router.py`-route les requêtes vers les outils appropriés via le LLM. Le fichier `plugin_loader.py` charge dynamiquement les plugins.

#### `src/tasks.py` et `src/goals.py`

Ces fichiers gèrent les données structurées du système. Le fichier `goals.py` store les objectifs utilisateur dans goals/goals.json avec priorité, mots-clés et progression. Le fichier `tasks.py` store les tâches générées dans tasks/tasks.json avec statut, steps, priorité et dates d'échéance.

### `plugins/` — Plugins d'Extension

Les plugins enrichissent le système avec des capacités supplémentaires. Le fichier `spotify_plugin.py` permet d'interagir avec Spotify (recherche, lecture). Le fichier `weather_plugin.py` récupère la météo via API externe. Le fichier `reminders_plugin.py` gère les rappels programmés.

### `src/ui/` — Interfaces Utilisateur

Le dossier ui/ contient les différentes interfaces. Le fichier `app.py` implémente le dashboard web Flask accessible via http://127.0.0.1:5000. Le fichier `telegram_bot.py` est le bot Telegram pour interagir à distance. Le dossier `static/` et `templates/` contain les ressources HTML/JS/CSS du dashboard.

### `data/` — Données

Le dossier data/ stocke toutes les données du système. Le sous-dossier `raw/` recoit les documents sources à ingérer. Le sous-dossier `processed/` contient le texte extrait en cache. Le sous-dossier `db/` accueille SQLite (metadata.db) et ChromaDB (chroma/). Les autres sous-dossiers (notes/, exports/) stockent les sorties du système.

### `logs/` et `goals/`, `tasks/`

Le dossier `logs/` stocke les journaux d'exécution (second_brain.log, tool_executions.json). Le dossier `goals/` stocke goals.json. Le dossier `tasks/` stocke tasks.json.

## Commandes Principales

L'outil s'utilise via `python main.py` suivi d'une commande. La commande **ingest** ingère les documents de data/raw/ (Parse → Chunk → Embed → Store). La commande **query** pose une question unique sur les documents. La commande **chat** ouvre le mode conversationnel interactif avec mémoire persistante. Les commandes **list** et **stats** listent les documents et affiche les statistiques système.

La commande **agent** démarre la boucle proactive multi-agents (Jarvis Mode). La commande **goals** gère les objectifs (--add pour en ajouter). La commande **tasks** gère les tâches (--pending, --done). La commande **tools** liste les outils et affiche l'audit log. La commande **dashboard** lance l'interface web. La commande **telegram** démarre le bot Telegram.

## Stack Technique

Le système utilise Python 3.11+ comme langage principal. ChromaDB gère le stockage vectoriel local. sentence-transformers (all-MiniLM-L6-v2) génère les embeddings. Ollama (Qwen2.5) fait tourner les modèles LLM localement. PyMuPDF parse les fichiers PDF. SQLite stocke les métadonnées. Rich formate la sortie CLI. Flask anime le dashboard web.

## Flux de Données Typeique

Le flux de données comienza quand l'utilisateur place des documents dans data/raw/ puis exécute `python main.py ingest`. Le système parse chaque fichier, le segmente en chunks, génère les embeddings et les stocke dans ChromaDB. Ensuite, l'utilisateur peut poser des questions via `python main.py query "question"` ou `python main.py chat`. Le pipeline RAG récupère les chunks pertinents, construit le prompt enrichi, génère la réponse via Ollama et la sauvegarde en mémoire.

En mode Jarvis via `python main.py agent`, le système charge les mémoires, les ranke par rapport aux objectifs, génère des insights, crée des tâches, et envoie des rappels proactifs.

## points Forts

Le système est entièrement local : aucune donnée ne quitte la machine. Il est modulaire et extensible via les plugins et outils. L'architecture multi-agents permet une analyse stratégique sophistiquée. La mémoire conversationnelle assure la continuité. Le mode proactif transforme le système d réactif à proactif.