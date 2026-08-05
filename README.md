# Application Web — Maintenance Prédictive TGV
**Mémoire M2 Data & IA — SNCF Voyageurs**

Application Flask de prédiction et de suivi de la maintenance des rames TGV,
développée dans le cadre d'un projet d'alternance à la STF (Supervision Technique de la Flotte).

---

## Prérequis

- Python 3.10+
- pip

---

## Installation

```bash
# 1. Cloner ou dézipper le projet
cd web_app

# 2. Créer un environnement virtuel (recommandé)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux / Mac

# 3. Installer les dépendances
pip install -r requirements.txt
```

---

## Configuration

Créer un fichier `.env` ou définir la variable d'environnement suivante :

```
GROQ_API_KEY=votre_cle_groq
```

> La clé Groq est nécessaire uniquement pour le chatbot.
> Sans cette clé, toutes les autres fonctionnalités de l'application restent disponibles.

---

## Lancement en local

```bash
python app.py
```

L'application démarre sur : http://127.0.0.1:5000

---

## Identifiants de connexion

| Identifiant | Mot de passe | Rôle |
|---|---|---|
| `user` | `user` | Programmeur |

---

## Structure du projet

```
web_app/
├── app.py                  # Application Flask principale
├── data_loader.py          # Chargement et traitement des données
├── chatbot.py              # Module chatbot (API Groq)
├── requirements.txt        # Dépendances Python
├── data_export/            # Données et modèles exportés depuis le notebook
│   ├── clf.pkl             # Modèle XGBoost calibré
│   ├── base_clf.pkl        # Modèle XGBoost de base
│   ├── encoders.pkl        # Encodeurs des variables catégorielles
│   ├── model_meta.json     # Métadonnées du modèle (accuracy, features)
│   ├── taux_hist.json      # Taux historiques par catégorie/code opération
│   ├── df_merge.pkl        # Dataset principal (interventions matchées)
│   └── df_prog_unmatched.pkl  # Planning non réalisé
├── templates/              # Pages HTML (Jinja2)
└── static/                 # CSS et images
```

---

## Fonctionnalités

- **Dashboard** : KPIs globaux, alertes non-conformités
- **Parc** : liste et détail des rames TGV
- **Planning** : calendrier des interventions (FullCalendar)
- **Historique** : évolution mensuelle des écarts
- **Prédiction** : probabilité de réalisation d'une opération (XGBoost)
- **Chatbot** : assistant conversationnel connecté aux données réelles (Groq)

---

## Données sources

- `dataProgone_S1-S12.xlsx` — données de planification PROGONE (S1-S12 2026)
- `data_S1_S12 réalisation.xlsx` — données de réalisation GMAO (S1-S12 2026)

> Ces fichiers ne sont pas inclus dans le ZIP pour des raisons de confidentialité SNCF.
> L'application fonctionne directement depuis les fichiers exportés (`data_export/`).

---

## Déploiement sur Render

1. Créer un compte sur [render.com](https://render.com)
2. Nouveau Web Service → uploader le dossier `web_app/`
3. **Start command** : `python app.py`
4. Ajouter la variable d'environnement `GROQ_API_KEY` dans les paramètres Render
