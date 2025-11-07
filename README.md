# CyberQuiz

Application web Flask permettant de tester ses connaissances en cybersécurité à l'aide d'affirmations Oui/Non.

## Prérequis

- Python 3.11+
- pip
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

Le script `ai/generator.py` simule une IA locale. Exécutez-le manuellement si besoin :
```bash
python ai/generator.py
```
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
