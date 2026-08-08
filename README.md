# Application Web — Maintenance Prédictive TGV
**Mémoire M2 Data & IA — SNCF Voyageurs**

Application Flask de prédiction et de suivi de la maintenance des rames TGV,
développée dans le cadre d'un projet d'alternance à la STF (Supervision Technique de la Flotte).

---

## URL publique

**Application en ligne** : https://tgv-maintenance-app.onrender.com

**Dépôt Git** : https://github.com/sarahchachoua2002-byte/tgv-maintenance-app

> Note : l'application est hébergée sur le plan gratuit de Render. Elle se met en veille après
> 15 minutes d'inactivité. Le premier accès après une période d'inactivité peut prendre
> 1 à 2 minutes le temps que le serveur se réveille. Ce comportement est normal.

---

## Identifiants de connexion

| Identifiant | Mot de passe | Rôle |
|---|---|---|
| `user` | `user` | Programmeur |

> Aucun compte administrateur back-office n'est requis — l'application est mono-profil.

---

## Compatibilité navigateurs

Testée et validée sur :
- Google Chrome (recommandé)
- Microsoft Edge
- Mozilla Firefox
- Opera

---

## Prérequis

- Python 3.10+
- pip

---

## Installation en local

```bash
# 1. Cloner ou dézipper le projet
cd web_app

# 2. Créer un environnement virtuel (recommandé)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux / Mac

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer l'application
python app.py
```

L'application démarre sur : http://127.0.0.1:5000

---

## Configuration (optionnelle)

Définir la variable d'environnement suivante pour activer le chatbot :

```
GROQ_API_KEY=votre_cle_groq
```

> Sans cette clé, toutes les autres fonctionnalités restent disponibles.

---

## Structure du projet

```
web_app/
├── app.py                      # Application Flask principale
├── data_loader.py              # Chargement et traitement des données
├── chatbot.py                  # Module chatbot (API Groq)
├── requirements.txt            # Dépendances Python
├── Procfile                    # Configuration déploiement Render (gunicorn)
├── data_export/                # Données et modèles exportés depuis le notebook
│   ├── clf.pkl                 # Modèle XGBoost calibré (classification)
│   ├── base_clf.pkl            # Modèle XGBoost de base
│   ├── encoders.pkl            # Encodeurs des variables catégorielles
│   ├── model_meta.json         # Métadonnées du modèle (accuracy, features)
│   ├── taux_hist.json          # Taux historiques par catégorie/code opération
│   ├── df_merge.pkl            # Dataset principal (interventions matchées)
│   ├── df_merge.parquet        # Dataset principal (format compressé)
│   ├── df_prog_clean.pkl       # Données PROGONE nettoyées
│   ├── df_prog_unmatched.pkl   # Planning non réalisé
│   ├── df_prog_unmatched.parquet
│   └── df_real_clean.pkl       # Données GMAO nettoyées
├── templates/                  # Pages HTML (Jinja2)
└── static/                     # CSS et images
```

---

## Fonctionnalités

- **Tableau de bord** : KPIs globaux, alertes non-conformités
- **Parc de rames** : liste et détail des rames TGV
- **Planning** : calendrier des interventions
- **Historique** : évolution mensuelle des écarts
- **Prédiction IA** : probabilité de réalisation d'une opération (XGBoost)
- **Chatbot** : assistant conversationnel connecté aux données réelles (Groq)

---

## Données sources

- `dataProgone_S1-S12.xlsx` — données de planification PROGONE (S1-S12 2026)
- `data_S1_S12 réalisation.xlsx` — données de réalisation GMAO (S1-S12 2026)

> Ces fichiers ne sont pas inclus dans ce dépôt Git pour des raisons de confidentialité SNCF Voyageurs.
> Ils sont fournis séparément dans le ZIP du livrable académique.
> L'application web fonctionne directement depuis les fichiers exportés (`data_export/`)
> et ne nécessite pas les fichiers Excel pour être déployée ou testée.
> Pour exécuter le notebook d'analyse complet, les fichiers Excel sources sont nécessaires
> et disponibles dans le ZIP remis à l'école.

## Base de données

Cette application n'utilise pas de base de données SQL.
Les données sont stockées sous forme de fichiers sérialisés (`.pkl`, `.parquet`, `.json`)
dans le répertoire `data_export/`, exportés depuis le notebook d'analyse.

> Il n'y a donc pas de fichier SQL dump à fournir.
