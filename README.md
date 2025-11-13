# CyberQuiz

Application web Flask permettant de tester ses connaissances en cybersécurité à l'aide d'affirmations Oui/Non.

## Prérequis

- Python 3.11+
- pip
- (Optionnel) [Ollama](https://ollama.com/) avec le modèle `llama3` téléchargé pour générer les questions automatiquement
- (Optionnel) Docker et Docker Compose
- (Optionnel mais recommandé) Connexion Internet lors du premier démarrage pour télécharger le modèle d'embedding `all-MiniLM-L6-v2` utilisé par le système RAG

## Installation locale

1. Créez un environnement virtuel et activez-le :
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows : .venv\Scripts\activate
   ```
2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Initialisez la base de données SQLite :
   ```bash
   python db/init_db.py
   ```
4. Lancez l'application :
   ```bash
   flask --app app run
   ```
5. Ouvrez votre navigateur sur http://127.0.0.1:5000.

### Activer la génération de questions via Ollama

1. Installez Ollama puis téléchargez le modèle `llama3` :
   ```bash
   ollama pull llama3
   ```
2. Lancez le serveur Ollama en local (il écoute par défaut sur `http://localhost:11434`).
3. Facultatif : définissez des variables d'environnement pour personnaliser la connexion :
   ```bash
   export OLLAMA_URL="http://localhost:11434"
   export OLLAMA_MODEL="llama3"
   ```
4. Depuis l'interface admin, utilisez le bouton « Générer de nouvelles questions ».

Vous pouvez guider l'IA en fournissant un thème ou un court contexte depuis l'interface administrateur (ou via la ligne de commande ci-dessous). Ces éléments sont transmis au moteur de RAG afin de générer des affirmations inédites tout en s'appuyant sur les connaissances existantes.

Si Ollama n'est pas disponible, l'application basculera automatiquement sur un jeu de questions locales prédéfinies.

## Utilisation

- **Page d'accueil** : choisissez un pseudo unique et un mode de jeu (classique, par thème ou chrono).
- **Quiz** : répondez par Oui/Non. En mode chrono, un timer de 30 secondes valide automatiquement la réponse à 0 seconde.
- **Scores** : consultez le top 10 des meilleurs scores.
- **Admin** : connectez-vous avec les identifiants par défaut (`admin` / `admin123`). Validez ou rejetez les questions en attente et lancez la génération de nouvelles questions via `ai/generator.py`.

## Docker

1. Construisez l'image :
   ```bash
   docker build -t cyberquiz .
   ```
2. Exécutez le conteneur :
   ```bash
   docker run -p 5000:5000 cyberquiz
   ```

### Docker Compose

```bash
docker-compose up --build
```

## Génération de questions IA

Le script `ai/generator.py` contacte Ollama pour générer de nouvelles affirmations Oui/Non.
Exécutez-le manuellement si besoin :
```bash
python ai/generator.py
```
Quelques options utiles :

```bash
# Concentrez la génération sur un thème spécifique
python ai/generator.py --theme "phishing"

# Ajoutez un contexte libre (ex : un public visé ou une contrainte)
python ai/generator.py --theme "mots de passe" --context "ciblé pour des collaborateurs débutants"
```

Assurez-vous qu'Ollama est lancé et que le modèle `llama3` est disponible. En cas d'indisponibilité,
le script utilise automatiquement un jeu de questions local (en appliquant le thème ou le contexte demandé).

Les questions générées sont insérées avec le statut `en_attente`. Validez-les via l'interface admin pour les rendre jouables.

### 🧠 Système RAG (Retrieval-Augmented Generation)

CyberQuiz intègre une base de connaissances vectorielle (ChromaDB) alimentée par les questions validées :

- la base est synchronisée automatiquement lors de `python db/init_db.py` ;
- chaque validation d'une question en admin l'ajoute instantanément à l'index vectoriel ;
- le générateur récupère les questions proches du thème ou du contexte demandé pour éviter les répétitions et enrichir le prompt Ollama.

Vous pouvez reconstruire la base vectorielle à tout moment (par exemple après un import massif) :

```bash
python -c "from ai import rag; rag.build_vector_db_from_sqlite()"
```

En cas d'absence de dépendances (Chromadb ou SentenceTransformers), l'application continue de fonctionner sans RAG et affiche un message d'information dans la console.

### 🔍 Gestion des doublons

Le générateur vérifie automatiquement les affirmations proposées avant de les insérer :

- comparaison textuelle stricte (après normalisation de la casse et des espaces) ;
- comparaison sémantique simple basée sur la similarité de `difflib.SequenceMatcher`.

Si un doublon est détecté, la question est ignorée et un message est affiché dans la console, par exemple :

```
[DUPLICATE] Question déjà existante : Les mises à jour logicielles corrigent souvent des failles de sécurité critiques.
```

### 🗑️ Suppression de la liste de validation

Depuis l'interface administrateur, le bouton « 🗑️ Supprimer toutes les questions en cours de validation » permet de vider d'un seul clic la liste des affirmations avec le statut `en_attente`. Les questions déjà validées ainsi que les scores enregistrés ne sont pas affectés.

### 🧩 Interaction avec la base SQLite

La base de données SQLite `cyberquiz.db` peut être explorée via le terminal :

```bash
sqlite3 cyberquiz.db
```

Quelques commandes utiles une fois dans la console `sqlite3` :

```sql
.tables            -- liste les tables disponibles
SELECT * FROM questions LIMIT 5;  -- apercu des questions
SELECT * FROM scores ORDER BY score DESC LIMIT 10;  -- top 10 des scores
```

## Structure du projet

```
.
├── ai/
│   ├── __init__.py
│   ├── generator.py
│   └── rag.py
├── app.py
├── db/
│   └── init_db.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── templates/
└── static/
```
