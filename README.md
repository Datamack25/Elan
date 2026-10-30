# 🚀 ÉLAN — Plateforme de financement de l'entrepreneuriat des jeunes

Plateforme Streamlit qui met en relation de **jeunes porteurs de projet (≤ 30 ans)** et des **investisseurs / contributeurs**, avec trois façons de soutenir un projet : **don avec contreparties (crowdfunding)**, **prêt rémunéré** ou **investissement au capital** (et un mode mixte).

## Fonctionnalités

| Module | Contenu |
|---|---|
| 🏠 Accueil | Chiffres clés, vitrine des projets financés, projets proches de l'objectif |
| 🔎 Explorer | Filtres (secteur, département, mode, ODD, statut, ticket max), **critères obligatoires**, score de critères minimum, **classement** par adéquation aux préférences, critères, impact, avancement, date limite… Vue cartes ou tableau |
| 📄 Fiche projet | Image, description, contreparties, financement (don / prêt / capital avec simulation de part ou de remboursement), impact visé vs constaté, checklist des critères, actualités, **questions publiques**, **message privé au porteur**, contributeurs |
| 🏆 Projets financés | Galerie avec image, montant levé, emplois créés, bénéficiaires, CO₂ évité |
| 🇭🇹 Carte d'Haïti | Sur l'accueil et en tête du tableau de bord : une bulle par département (10), taille et couleur selon l'indicateur choisi — projets soutenus, montant levé, projets financés, emplois créés, contributeurs. Tableau par département exportable |
| 📊 Statistiques | Collecte mensuelle et cumulée, modes de financement, secteurs, départements, taux de réussite, impact, ODD, qualité vs impact, classements, export CSV |
| 💬 Messagerie | Conversations privées investisseurs ↔ porteurs, par projet, avec non-lus |
| 🚀 Soumettre | Formulaire complet (image, financement, impact, ODD, justificatifs, engagements) → validation par l'équipe |
| 👤 Mon espace | Porteur : suivi de collecte, publication d'actualités et de résultats d'impact. Investisseur : portefeuille, **préférences et pondérations du classement**, favoris, recommandations. KYC pour tous |
| 🛡️ Administration | Modération des projets, validation KYC, **alertes LCB-FT** sur les contributions, utilisateurs |

### Scores
- **Score de critères (0-100)** : KYC du porteur (20), porteur ≤ 30 ans (10), business plan (15), structure immatriculée (15), charte ESG (10), objectifs d'impact chiffrés (15), équipe ≥ 2 (5), engagement de reporting (10). Pondérations modifiables dans `db.CRITERIA`.
- **Score d'impact (0-100)** : emplois, bénéficiaires, CO₂ évité (échelle logarithmique) et nombre d'ODD.
- **Score d'adéquation (0-100)** : correspondance avec les préférences de l'investisseur, pondérations réglables par l'investisseur.

### Contrôles LCB-FT intégrés (paramétrables dans `db.py`)
- KYC vérifié obligatoire pour tout prêt ou investissement au capital, et au-delà de 1 000 € de contributions cumulées.
- Contribution unitaire ≥ 5 000 € ou > 150 % du reste à financer → mise en revue par l'équipe conformité.
- Clôture automatique des collectes (financé / objectif non atteint).

## Lancement

```bash
pip install -r requirements.txt
streamlit run app.py
```

La base SQLite `data/elan.db` est créée au premier lancement avec des données de démonstration (16 projets, contributions sur 12 mois, échanges). Supprimez le fichier pour repartir de zéro.

**Comptes de démonstration** (mot de passe `demo1234`) : `porteur1@elan.fr` … `porteur8@elan.fr`, `investisseur1@elan.fr` … `investisseur6@elan.fr`, `admin@elan.fr`.

## Structure

```
app.py               interface Streamlit (pages, cartes, graphiques)
db.py                données, authentification, scores, contrôles LCB-FT, jeu de démo
.streamlit/config.toml
requirements.txt
data/                base SQLite (ignorée par git)
```

## Déploiement Streamlit Cloud
L'initialisation de la base est protégée contre les démarrages simultanés (verrou + `st.cache_resource`) : l'erreur `sqlite3.IntegrityError` sur `admin@elan.fr` ne peut plus se produire. Une base restée à moitié amorcée après un plantage est purgée et ré-amorcée automatiquement, à condition qu'elle ne contienne que des comptes de démonstration (`@elan.fr`).

La carte utilise le fond de carte gratuit Carto (aucune clé API).

Sur Streamlit Community Cloud, le disque n'est pas persistant : la base est recréée à chaque redémarrage. Pour une utilisation réelle, remplacez SQLite par une base hébergée (PostgreSQL / Supabase) et stockez les images dans un stockage objet.

## Avant une mise en production réelle
Les paiements sont **simulés**. Opérer en France une plateforme de prêt ou d'investissement participatif exige l'agrément **PSFP** (règlement UE 2020/1503) délivré par l'AMF, un partenariat avec un établissement de paiement agréé (comptes de cantonnement), un dispositif LCB-FT complet (KYC documentaire, filtrage sanctions/PPE, déclarations Tracfin) et la fiche d'informations clés (KIIS) par projet.
