# CyberQuiz

Application web Flask permettant de tester ses connaissances en cybersécurité à l'aide d'affirmations Oui/Non.

## Prérequis

- Python 3.11+
- pip
- (Optionnel) [Ollama](https://ollama.com/) avec le modèle `llama3` téléchargé pour générer les questions automatiquement
- (Optionnel) Docker et Docker Compose

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
Assurez-vous qu'Ollama est lancé et que le modèle `llama3` est disponible. En cas d'indisponibilité,
le script utilise automatiquement un jeu de questions local.

Les questions générées sont insérées avec le statut `en_attente`. Validez-les via l'interface admin pour les rendre jouables.

## Structure du projet

```
.
├── ai/
│   └── generator.py
├── app.py
├── db/
│   └── init_db.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── templates/
└── static/
```
