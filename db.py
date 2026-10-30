"""Couche de données de la plateforme ÉLAN (SQLite).

Contient : schéma, authentification, logique métier (scores, statuts,
contrôles LCB-FT simplifiés) et jeu de données de démonstration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("ELAN_DB", Path(__file__).parent / "data" / "elan.db"))

# --------------------------------------------------------------------------
# Référentiels
# --------------------------------------------------------------------------
SECTORS = {
    "AgriTech & Alimentation": "🌱",
    "Énergie & Climat": "⚡",
    "Économie circulaire": "♻️",
    "Éducation": "🎓",
    "Santé & Bien-être": "🩺",
    "Numérique & Tech": "💻",
    "Culture & Création": "🎨",
    "Mode durable": "👕",
    "Mobilité": "🚲",
    "Tourisme responsable": "🧭",
    "Économie sociale & solidaire": "🤝",
}

REGIONS = [
    "Île-de-France", "Auvergne-Rhône-Alpes", "Hauts-de-France", "Occitanie",
    "Nouvelle-Aquitaine", "Provence-Alpes-Côte d'Azur", "Grand Est",
    "Bretagne", "Pays de la Loire", "Guadeloupe", "Martinique", "Guyane",
    "La Réunion", "Mayotte",
]

MODES = {
    "don": "Don / récompense (crowdfunding)",
    "pret": "Prêt rémunéré",
    "equity": "Investissement au capital",
    "mixte": "Mixte (don + investissement)",
}

ODD = {
    1: "Pas de pauvreté", 2: "Faim « zéro »", 3: "Bonne santé", 4: "Éducation de qualité",
    5: "Égalité femmes-hommes", 6: "Eau propre", 7: "Énergie propre", 8: "Travail décent",
    9: "Industrie & innovation", 10: "Inégalités réduites", 11: "Villes durables",
    12: "Consommation responsable", 13: "Climat", 14: "Vie aquatique",
    15: "Vie terrestre", 16: "Paix & justice", 17: "Partenariats",
}

# Critères de conformité / qualité d'un projet : (clé, libellé, poids)
CRITERIA = [
    ("kyc", "Identité du porteur vérifiée (KYC)", 20),
    ("young", "Porteur de 30 ans ou moins", 10),
    ("business_plan", "Business plan fourni", 15),
    ("legal_entity", "Structure juridique immatriculée", 15),
    ("esg_charter", "Charte ESG / éthique signée", 10),
    ("impact_targets", "Objectifs d'impact chiffrés", 15),
    ("team", "Équipe de 2 personnes ou plus", 5),
    ("impact_report", "Engagement de reporting d'impact", 10),
]
CRITERIA_LABELS = {k: lbl for k, lbl, _ in CRITERIA}

STATUS_LABELS = {
    "en_revue": "En revue",
    "en_cours": "En collecte",
    "finance": "Financé",
    "echoue": "Objectif non atteint",
    "rejete": "Refusé",
}

# Seuils LCB-FT (simplifiés, paramétrables)
KYC_THRESHOLD = 1000          # cumul par contributeur au-delà duquel le KYC vérifié est exigé
ALERT_SINGLE_AMOUNT = 5000    # contribution unitaire déclenchant une revue manuelle
EQUITY_MIN_KYC = True         # tout investissement en capital ou prêt exige un KYC vérifié

PALETTES = [
    ("#0f766e", "#5eead4"), ("#1d4ed8", "#93c5fd"), ("#7c3aed", "#c4b5fd"),
    ("#b45309", "#fcd34d"), ("#be123c", "#fda4af"), ("#15803d", "#86efac"),
    ("#0e7490", "#67e8f9"), ("#a21caf", "#f0abfc"), ("#c2410c", "#fdba74"),
]


# --------------------------------------------------------------------------
# Connexion & schéma
# --------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    pwd_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('porteur','investisseur','admin')),
    kyc_status TEXT NOT NULL DEFAULT 'non_verifie',
    birth_year INTEGER,
    city TEXT,
    bio TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    tagline TEXT,
    description TEXT,
    sector TEXT, region TEXT, mode TEXT,
    goal REAL NOT NULL,
    min_ticket REAL DEFAULT 10,
    equity_pct REAL, valuation REAL,
    interest_rate REAL, duration_months INTEGER,
    rewards TEXT,
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'en_revue',
    image TEXT, image_mime TEXT,
    palette INTEGER DEFAULT 0,
    jobs_target INTEGER DEFAULT 0,
    beneficiaries_target INTEGER DEFAULT 0,
    co2_target REAL DEFAULT 0,
    odd TEXT,
    business_plan INTEGER DEFAULT 0,
    legal_entity INTEGER DEFAULT 0,
    esg_charter INTEGER DEFAULT 0,
    impact_report INTEGER DEFAULT 0,
    team_size INTEGER DEFAULT 1,
    founder_age INTEGER,
    admin_note TEXT,
    created_at TEXT NOT NULL,
    funded_at TEXT
);
CREATE TABLE IF NOT EXISTS contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount REAL NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('don','pret','equity')),
    status TEXT NOT NULL DEFAULT 'confirme',
    alert TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT, body TEXT,
    jobs_created INTEGER DEFAULT 0,
    beneficiaries INTEGER DEFAULT 0,
    co2_avoided REAL DEFAULT 0,
    revenue REAL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    sender_id INTEGER NOT NULL REFERENCES users(id),
    recipient_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    parent_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    PRIMARY KEY (user_id, project_id)
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db(seed: bool = True) -> None:
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    empty = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    con.close()
    if seed and empty:
        seed_demo()
    refresh_statuses()


# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------
def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


def create_user(email, name, password, role, birth_year=None, city=None, bio=None,
                kyc_status="non_verifie", created_at=None) -> int:
    salt = secrets.token_hex(16)
    con = connect()
    cur = con.execute(
        "INSERT INTO users(email,name,pwd_hash,salt,role,kyc_status,birth_year,city,bio,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (email.strip().lower(), name.strip(), _hash(password, salt), salt, role, kyc_status,
         birth_year, city, bio, created_at or now()),
    )
    con.commit()
    uid = cur.lastrowid
    con.close()
    return uid


def authenticate(email: str, password: str):
    con = connect()
    row = con.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    con.close()
    if row and secrets.compare_digest(row["pwd_hash"], _hash(password, row["salt"])):
        return dict(row)
    return None


def get_user(uid: int):
    con = connect()
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return dict(row) if row else None


def set_kyc(uid: int, status: str) -> None:
    con = connect()
    con.execute("UPDATE users SET kyc_status=? WHERE id=?", (status, uid))
    con.commit()
    con.close()


def list_users():
    con = connect()
    rows = [dict(r) for r in con.execute("SELECT id,email,name,role,kyc_status,birth_year,city,created_at FROM users ORDER BY id")]
    con.close()
    return rows


# --------------------------------------------------------------------------
# Projets
# --------------------------------------------------------------------------
def svg_cover(title: str, sector: str, palette: int, w: int = 800, h: int = 450) -> str:
    """Génère une couverture SVG (data URI) quand aucune image n'est fournie."""
    c1, c2 = PALETTES[palette % len(PALETTES)]
    icon = SECTORS.get(sector, "🚀")
    safe = (title or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rnd = random.Random(title)
    circles = "".join(
        f'<circle cx="{rnd.randint(0, w)}" cy="{rnd.randint(0, h)}" r="{rnd.randint(30, 160)}" '
        f'fill="#ffffff" opacity="{rnd.uniform(0.04, 0.12):.2f}"/>' for _ in range(7)
    )
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}'>
<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
<stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/></linearGradient></defs>
<rect width='{w}' height='{h}' fill='url(#g)'/>{circles}
<text x='50%' y='46%' text-anchor='middle' font-size='120'>{icon}</text>
<text x='50%' y='78%' text-anchor='middle' font-family='Segoe UI,Helvetica,Arial,sans-serif' font-size='40' font-weight='700' fill='#ffffff'>{safe[:34]}</text>
</svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def image_uri(p: dict) -> str:
    if p.get("image"):
        return f"data:{p.get('image_mime') or 'image/png'};base64,{p['image']}"
    return svg_cover(p["title"], p["sector"], p.get("palette") or 0)


def create_project(owner_id: int, data: dict) -> int:
    cols = ["owner_id", "title", "tagline", "description", "sector", "region", "mode", "goal",
            "min_ticket", "equity_pct", "valuation", "interest_rate", "duration_months", "rewards",
            "deadline", "status", "image", "image_mime", "palette", "jobs_target",
            "beneficiaries_target", "co2_target", "odd", "business_plan", "legal_entity",
            "esg_charter", "impact_report", "team_size", "founder_age", "created_at", "funded_at"]
    data = {**data, "owner_id": owner_id}
    data.setdefault("status", "en_revue")
    data.setdefault("created_at", now())
    data.setdefault("palette", random.randint(0, len(PALETTES) - 1))
    vals = [data.get(c) for c in cols]
    con = connect()
    cur = con.execute(f"INSERT INTO projects({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    con.commit()
    pid = cur.lastrowid
    con.close()
    return pid


def update_project(pid: int, **fields) -> None:
    if not fields:
        return
    con = connect()
    con.execute(f"UPDATE projects SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                [*fields.values(), pid])
    con.commit()
    con.close()


def projects_df(include_hidden: bool = False):
    """Tous les projets enrichis : montant levé, contributeurs, impact réalisé, scores."""
    import pandas as pd

    con = connect()
    q = """
    SELECT p.*, u.name AS owner_name, u.kyc_status AS owner_kyc, u.city AS owner_city,
      COALESCE((SELECT SUM(amount) FROM contributions c WHERE c.project_id=p.id AND c.status='confirme'),0) AS raised,
      COALESCE((SELECT COUNT(DISTINCT user_id) FROM contributions c WHERE c.project_id=p.id AND c.status='confirme'),0) AS backers,
      COALESCE((SELECT SUM(jobs_created) FROM updates x WHERE x.project_id=p.id),0) AS jobs_done,
      COALESCE((SELECT SUM(beneficiaries) FROM updates x WHERE x.project_id=p.id),0) AS benef_done,
      COALESCE((SELECT SUM(co2_avoided) FROM updates x WHERE x.project_id=p.id),0) AS co2_done,
      COALESCE((SELECT COUNT(*) FROM comments m WHERE m.project_id=p.id),0) AS n_comments
    FROM projects p JOIN users u ON u.id=p.owner_id
    """
    df = pd.read_sql_query(q, con)
    con.close()
    if df.empty:
        return df
    if not include_hidden:
        df = df[df["status"].isin(["en_cours", "finance", "echoue"])]
    df = df.copy()
    df["pct"] = (df["raised"] / df["goal"]).clip(lower=0) * 100
    df["deadline_dt"] = pd.to_datetime(df["deadline"], errors="coerce")
    df["days_left"] = (df["deadline_dt"] - pd.Timestamp.now()).dt.days
    df["odd_list"] = df["odd"].fillna("").apply(lambda s: [int(x) for x in str(s).split(",") if x.strip().isdigit()])
    crit = df.apply(criteria_status, axis=1)
    df["criteria"] = crit
    df["criteria_score"] = crit.apply(criteria_score)
    df["impact_score"] = df.apply(impact_score, axis=1)
    return df


def get_project(pid: int):
    df = projects_df(include_hidden=True)
    row = df[df["id"] == pid]
    return row.iloc[0].to_dict() if not row.empty else None


def criteria_status(p) -> dict:
    return {
        "kyc": p["owner_kyc"] == "verifie",
        "young": (p["founder_age"] or 99) <= 30,
        "business_plan": bool(p["business_plan"]),
        "legal_entity": bool(p["legal_entity"]),
        "esg_charter": bool(p["esg_charter"]),
        "impact_targets": (p["jobs_target"] or 0) > 0 or (p["beneficiaries_target"] or 0) > 0 or (p["co2_target"] or 0) > 0,
        "team": (p["team_size"] or 1) >= 2,
        "impact_report": bool(p["impact_report"]),
    }


def criteria_score(status: dict) -> float:
    return float(sum(w for k, _, w in CRITERIA if status.get(k)))


def impact_score(p) -> float:
    """Score d'impact 0-100 (objectifs déclarés + impact constaté + couverture ODD)."""
    import math

    jobs = max(p["jobs_target"] or 0, p.get("jobs_done", 0) or 0)
    ben = max(p["beneficiaries_target"] or 0, p.get("benef_done", 0) or 0)
    co2 = max(p["co2_target"] or 0, p.get("co2_done", 0) or 0)
    n_odd = len(p["odd_list"]) if "odd_list" in p else 0
    s = (min(math.log1p(jobs) / math.log1p(30), 1) * 30
         + min(math.log1p(ben) / math.log1p(5000), 1) * 30
         + min(math.log1p(co2) / math.log1p(500), 1) * 25
         + min(n_odd / 4, 1) * 15)
    return round(s, 1)


def match_score(p, prefs: dict) -> float:
    """Score d'adéquation 0-100 entre un projet et les préférences d'un investisseur."""
    if not prefs:
        return round(0.5 * p["criteria_score"] + 0.5 * p["impact_score"], 1)
    w = {"sector": 25, "region": 15, "mode": 15, "odd": 15, "ticket": 10, "criteria": 20}
    w.update(prefs.get("weights", {}))
    total = sum(w.values()) or 1
    s = 0.0
    s += w["sector"] * (1 if not prefs.get("sectors") or p["sector"] in prefs["sectors"] else 0)
    s += w["region"] * (1 if not prefs.get("regions") or p["region"] in prefs["regions"] else 0)
    if not prefs.get("modes"):
        s += w["mode"]
    elif p["mode"] in prefs["modes"] or (p["mode"] == "mixte" and set(prefs["modes"]) & {"don", "equity"}):
        s += w["mode"]
    if prefs.get("odd"):
        overlap = len(set(prefs["odd"]) & set(p["odd_list"]))
        s += w["odd"] * min(overlap / max(1, min(len(prefs["odd"]), 3)), 1)
    else:
        s += w["odd"]
    budget = prefs.get("max_ticket") or 0
    s += w["ticket"] * (1 if not budget or (p["min_ticket"] or 0) <= budget else 0)
    s += w["criteria"] * p["criteria_score"] / 100
    return round(100 * s / total, 1)


def refresh_statuses() -> None:
    """Clôture automatique : financé si objectif atteint, échec si date limite dépassée."""
    con = connect()
    rows = con.execute(
        """SELECT p.id, p.goal, p.deadline,
           COALESCE((SELECT SUM(amount) FROM contributions c WHERE c.project_id=p.id AND c.status='confirme'),0) raised
           FROM projects p WHERE p.status='en_cours'"""
    ).fetchall()
    today = datetime.now().date().isoformat()
    for r in rows:
        if r["raised"] >= r["goal"]:
            con.execute("UPDATE projects SET status='finance', funded_at=? WHERE id=?", (now(), r["id"]))
        elif r["deadline"] and r["deadline"] < today:
            con.execute("UPDATE projects SET status='echoue' WHERE id=?", (r["id"],))
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Contributions (avec contrôles LCB-FT simplifiés)
# --------------------------------------------------------------------------
def user_total_contributed(uid: int) -> float:
    con = connect()
    v = con.execute("SELECT COALESCE(SUM(amount),0) FROM contributions WHERE user_id=? AND status!='refuse'", (uid,)).fetchone()[0]
    con.close()
    return float(v)


def check_contribution(user: dict, project: dict, amount: float, kind: str):
    """Retourne (autorisé: bool, message bloquant ou None, alerte éventuelle)."""
    if project["status"] != "en_cours":
        return False, "Ce projet n'est plus en collecte.", None
    if project["owner_id"] == user["id"]:
        return False, "Vous ne pouvez pas financer votre propre projet.", None
    if amount < (project["min_ticket"] or 1):
        return False, f"Le ticket minimum est de {project['min_ticket']:,.0f} €.".replace(",", " "), None
    verified = user["kyc_status"] == "verifie"
    if kind in ("pret", "equity") and EQUITY_MIN_KYC and not verified:
        return False, "Un prêt ou un investissement au capital exige une identité vérifiée (KYC). Rendez-vous dans « Mon espace ».", None
    cumul = user_total_contributed(user["id"]) + amount
    if cumul > KYC_THRESHOLD and not verified:
        return False, (f"Au-delà de {KYC_THRESHOLD:,} € de contributions cumulées, la vérification d'identité est requise "
                       "(obligations LCB-FT).").replace(",", " "), None
    alert = None
    if amount >= ALERT_SINGLE_AMOUNT:
        alert = f"Montant unitaire ≥ {ALERT_SINGLE_AMOUNT:,} € — revue manuelle".replace(",", " ")
    remaining = project["goal"] - project["raised"]
    if amount > remaining * 1.5 and remaining > 0:
        alert = (alert + " ; " if alert else "") + "Montant très supérieur au reste à financer"
    return True, None, alert


def add_contribution(project_id, user_id, amount, kind, created_at=None, alert=None) -> None:
    status = "en_revue" if alert else "confirme"
    con = connect()
    con.execute("INSERT INTO contributions(project_id,user_id,amount,kind,status,alert,created_at) VALUES (?,?,?,?,?,?,?)",
                (project_id, user_id, amount, kind, status, alert, created_at or now()))
    con.commit()
    con.close()
    refresh_statuses()


def set_contribution_status(cid: int, status: str) -> None:
    con = connect()
    con.execute("UPDATE contributions SET status=? WHERE id=?", (status, cid))
    con.commit()
    con.close()
    refresh_statuses()


def contributions_df():
    import pandas as pd

    con = connect()
    df = pd.read_sql_query(
        """SELECT c.*, p.title, p.sector, p.region, p.mode, u.name AS contributor, u.kyc_status
           FROM contributions c JOIN projects p ON p.id=c.project_id JOIN users u ON u.id=c.user_id""", con)
    con.close()
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


# --------------------------------------------------------------------------
# Échanges : messagerie privée & questions publiques
# --------------------------------------------------------------------------
def send_message(sender, recipient, body, project_id=None, created_at=None, is_read=0) -> None:
    con = connect()
    con.execute("INSERT INTO messages(project_id,sender_id,recipient_id,body,is_read,created_at) VALUES (?,?,?,?,?,?)",
                (project_id, sender, recipient, body.strip(), is_read, created_at or now()))
    con.commit()
    con.close()


def conversations(uid: int):
    """Liste des conversations (par interlocuteur et projet)."""
    con = connect()
    rows = con.execute(
        """SELECT CASE WHEN sender_id=? THEN recipient_id ELSE sender_id END AS other,
                  project_id, MAX(created_at) AS last_at,
                  SUM(CASE WHEN recipient_id=? AND is_read=0 THEN 1 ELSE 0 END) AS unread
           FROM messages WHERE sender_id=? OR recipient_id=?
           GROUP BY other, project_id ORDER BY last_at DESC""", (uid, uid, uid, uid)).fetchall()
    out = []
    for r in rows:
        other = con.execute("SELECT name, role FROM users WHERE id=?", (r["other"],)).fetchone()
        proj = con.execute("SELECT title FROM projects WHERE id=?", (r["project_id"],)).fetchone() if r["project_id"] else None
        last = con.execute(
            """SELECT body FROM messages WHERE ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))
               AND COALESCE(project_id,0)=COALESCE(?,0) ORDER BY created_at DESC LIMIT 1""",
            (uid, r["other"], r["other"], uid, r["project_id"])).fetchone()
        out.append({**dict(r), "other_name": other["name"], "other_role": other["role"],
                    "project_title": proj["title"] if proj else "Général", "last": last["body"] if last else ""})
    con.close()
    return out


def thread(uid: int, other: int, project_id):
    con = connect()
    rows = [dict(r) for r in con.execute(
        """SELECT m.*, u.name AS sender_name FROM messages m JOIN users u ON u.id=m.sender_id
           WHERE ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))
           AND COALESCE(project_id,0)=COALESCE(?,0) ORDER BY created_at""",
        (uid, other, other, uid, project_id))]
    con.execute("UPDATE messages SET is_read=1 WHERE recipient_id=? AND sender_id=? AND COALESCE(project_id,0)=COALESCE(?,0)",
                (uid, other, project_id))
    con.commit()
    con.close()
    return rows


def unread_count(uid: int) -> int:
    con = connect()
    n = con.execute("SELECT COUNT(*) FROM messages WHERE recipient_id=? AND is_read=0", (uid,)).fetchone()[0]
    con.close()
    return n


def add_comment(project_id, user_id, body, parent_id=None, created_at=None) -> None:
    con = connect()
    con.execute("INSERT INTO comments(project_id,user_id,body,parent_id,created_at) VALUES (?,?,?,?,?)",
                (project_id, user_id, body.strip(), parent_id, created_at or now()))
    con.commit()
    con.close()


def comments(project_id):
    con = connect()
    rows = [dict(r) for r in con.execute(
        """SELECT c.*, u.name, u.role FROM comments c JOIN users u ON u.id=c.user_id
           WHERE project_id=? ORDER BY created_at""", (project_id,))]
    con.close()
    return rows


# --------------------------------------------------------------------------
# Actualités / impact réalisé
# --------------------------------------------------------------------------
def add_update(project_id, title, body, jobs=0, benef=0, co2=0.0, revenue=0.0, created_at=None) -> None:
    con = connect()
    con.execute("INSERT INTO updates(project_id,title,body,jobs_created,beneficiaries,co2_avoided,revenue,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)", (project_id, title, body, jobs, benef, co2, revenue, created_at or now()))
    con.commit()
    con.close()


def updates(project_id):
    con = connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM updates WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
    con.close()
    return rows


def contributors(project_id):
    con = connect()
    rows = [dict(r) for r in con.execute(
        """SELECT u.id, u.name, SUM(c.amount) AS total, GROUP_CONCAT(DISTINCT c.kind) AS kinds, MAX(c.created_at) AS last
           FROM contributions c JOIN users u ON u.id=c.user_id WHERE c.project_id=? AND c.status='confirme'
           GROUP BY u.id ORDER BY total DESC""", (project_id,))]
    con.close()
    return rows


# --------------------------------------------------------------------------
# Préférences & favoris
# --------------------------------------------------------------------------
def get_prefs(uid: int) -> dict:
    con = connect()
    r = con.execute("SELECT data FROM preferences WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return json.loads(r["data"]) if r else {}


def save_prefs(uid: int, prefs: dict) -> None:
    con = connect()
    con.execute("INSERT INTO preferences(user_id,data) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                (uid, json.dumps(prefs, ensure_ascii=False)))
    con.commit()
    con.close()


def favorites(uid: int) -> set:
    con = connect()
    s = {r[0] for r in con.execute("SELECT project_id FROM favorites WHERE user_id=?", (uid,))}
    con.close()
    return s


def toggle_favorite(uid: int, pid: int) -> None:
    con = connect()
    if con.execute("SELECT 1 FROM favorites WHERE user_id=? AND project_id=?", (uid, pid)).fetchone():
        con.execute("DELETE FROM favorites WHERE user_id=? AND project_id=?", (uid, pid))
    else:
        con.execute("INSERT INTO favorites VALUES (?,?)", (uid, pid))
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# Données de démonstration
# --------------------------------------------------------------------------
DEMO_PASSWORD = "demo1234"

DEMO_PROJECTS = [
    # titre, accroche, secteur, région, mode, objectif, âge, avancement(0-1.3), statut, jobs, bénéf, co2, odd
    ("Kalbas Kréyòl", "Une conserverie artisanale de fruits locaux anti-gaspillage", "AgriTech & Alimentation", "Guadeloupe", "mixte", 45000, 26, 1.12, "finance", 6, 1200, 35, "2,8,12"),
    ("SolarKids", "Kits solaires pédagogiques pour les écoles rurales", "Énergie & Climat", "Guyane", "don", 18000, 24, 1.31, "finance", 3, 2400, 60, "4,7,13"),
    ("ReFab Lab", "Atelier de reconditionnement d'électroménager en insertion", "Économie circulaire", "Hauts-de-France", "pret", 60000, 29, 1.05, "finance", 9, 800, 140, "8,12,13"),
    ("Mentor'Up", "Plateforme de mentorat pour lycéens des quartiers prioritaires", "Éducation", "Île-de-France", "equity", 120000, 27, 1.0, "finance", 7, 3500, 0, "4,10"),
    ("Pédal'Eau", "Livraison du dernier kilomètre en vélo-cargo électrique", "Mobilité", "Auvergne-Rhône-Alpes", "equity", 90000, 28, 1.08, "finance", 12, 0, 210, "11,13"),
    ("Fil Vert", "Mode upcyclée à partir de textiles de seconde main", "Mode durable", "Occitanie", "don", 15000, 22, 1.18, "finance", 2, 600, 18, "5,12"),
    ("TéléSoins Péyi", "Téléconsultation et suivi des patients isolés", "Santé & Bien-être", "Martinique", "equity", 150000, 30, 0.62, "en_cours", 10, 5000, 0, "3,10"),
    ("Ruche Urbaine", "Ruchers en toiture et ateliers de sensibilisation", "AgriTech & Alimentation", "Nouvelle-Aquitaine", "don", 12000, 23, 0.74, "en_cours", 2, 900, 4, "15,11"),
    ("CodeLakou", "École de code gratuite pour les 16-25 ans", "Numérique & Tech", "La Réunion", "mixte", 70000, 25, 0.48, "en_cours", 5, 400, 0, "4,8,10"),
    ("Studio Marronnage", "Studio de création musicale et transmission culturelle", "Culture & Création", "Guadeloupe", "don", 25000, 21, 0.35, "en_cours", 3, 1500, 0, "4,11"),
    ("Aqua Mayotte", "Filtres à eau low-tech fabriqués localement", "Économie sociale & solidaire", "Mayotte", "pret", 40000, 27, 0.83, "en_cours", 6, 7000, 12, "6,3,1"),
    ("Hélios Coop", "Coopérative citoyenne de panneaux solaires sur toits publics", "Énergie & Climat", "Bretagne", "pret", 80000, 29, 0.56, "en_cours", 4, 0, 320, "7,13,17"),
    ("Sentiers Vivants", "Écotourisme encadré par de jeunes guides locaux", "Tourisme responsable", "Guyane", "mixte", 35000, 24, 0.22, "en_cours", 8, 2000, 10, "8,15"),
    ("Cantine Solidaire 13", "Traiteur d'insertion zéro déchet", "Économie sociale & solidaire", "Provence-Alpes-Côte d'Azur", "don", 20000, 26, 0.91, "en_cours", 5, 3000, 8, "2,8,12"),
    ("Grain de Sel", "Épicerie vrac itinérante en zone rurale", "Économie circulaire", "Grand Est", "don", 14000, 22, 0.41, "echoue", 2, 700, 6, "12"),
    ("NeuroPlay", "Jeux sérieux pour la rééducation des enfants", "Santé & Bien-être", "Pays de la Loire", "equity", 200000, 31, 0.0, "en_revue", 6, 1000, 0, "3,4"),
]

DEMO_PORTEURS = [
    ("Maëlys Désir", "Pointe-à-Pitre"), ("Kévin Ho-A-Sim", "Cayenne"), ("Inès Belkacem", "Roubaix"),
    ("Moussa Diarra", "Saint-Denis"), ("Léa Martin", "Lyon"), ("Chloé Fabre", "Toulouse"),
    ("Jordan Lise", "Fort-de-France"), ("Anaïs Dubreuil", "Bordeaux"),
]
DEMO_INVESTORS = [
    ("Paul Lemoine", "Business angel — impact & édutech", "verifie"),
    ("Fonds Horizon Jeunes", "Fonds d'amorçage à impact", "verifie"),
    ("Sarah Benali", "Particulière engagée, dons réguliers", "verifie"),
    ("Thomas Girard", "Investisseur particulier, climat", "en_cours"),
    ("Amandine Roux", "Contributrice crowdfunding", "non_verifie"),
    ("Diaspora Invest", "Club d'investisseurs de la diaspora caribéenne", "verifie"),
]


def seed_demo() -> None:
    rnd = random.Random(42)
    base = datetime.now()

    create_user("admin@elan.fr", "Équipe ÉLAN", DEMO_PASSWORD, "admin", kyc_status="verifie",
                created_at=(base - timedelta(days=400)).isoformat(timespec="seconds"))
    porteurs = []
    for i, (name, city) in enumerate(DEMO_PORTEURS):
        email = f"porteur{i + 1}@elan.fr"
        porteurs.append(create_user(email, name, DEMO_PASSWORD, "porteur", birth_year=1996 + i % 6, city=city,
                                    kyc_status="verifie" if i != 6 else "en_cours",
                                    created_at=(base - timedelta(days=380 - i * 10)).isoformat(timespec="seconds")))
    investors = []
    for i, (name, bio, kyc) in enumerate(DEMO_INVESTORS):
        investors.append(create_user(f"investisseur{i + 1}@elan.fr", name, DEMO_PASSWORD, "investisseur", bio=bio,
                                     kyc_status=kyc, city=rnd.choice(["Paris", "Lyon", "Pointe-à-Pitre", "Nantes"]),
                                     created_at=(base - timedelta(days=360 - i * 7)).isoformat(timespec="seconds")))

    descriptions = (
        "**Le constat** — {tag}. Les jeunes du territoire manquent d'accès au financement et aux réseaux.\n\n"
        "**Notre solution** — Un modèle économique sobre, ancré localement, qui crée des emplois durables "
        "et mesure son impact chaque trimestre.\n\n"
        "**Utilisation des fonds** — 45 % équipement, 30 % recrutement et formation, 15 % communication, 10 % trésorerie."
    )
    for i, (title, tag, sector, region, mode, goal, age, prog, status, jobs, ben, co2, odd) in enumerate(DEMO_PROJECTS):
        owner = porteurs[i % len(porteurs)]
        created = base - timedelta(days=rnd.randint(150, 330) if status in ("finance", "echoue") else rnd.randint(20, 80))
        if status == "finance":
            deadline = created + timedelta(days=60)
        elif status == "echoue":
            deadline = base - timedelta(days=12)
        else:
            deadline = base + timedelta(days=rnd.randint(10, 75))
        data = dict(
            title=title, tagline=tag, description=descriptions.format(tag=tag), sector=sector, region=region,
            mode=mode, goal=goal, min_ticket=10 if mode == "don" else (100 if mode == "pret" else (250 if mode == "equity" else 20)),
            equity_pct=round(goal / (goal * rnd.uniform(6, 12)) * 100, 1) if mode in ("equity", "mixte") else None,
            valuation=goal * rnd.randint(6, 12) if mode in ("equity", "mixte") else None,
            interest_rate=round(rnd.uniform(3.5, 6.5), 1) if mode == "pret" else None,
            duration_months=rnd.choice([24, 36, 48]) if mode == "pret" else None,
            rewards="10 € : remerciement · 50 € : produit offert · 200 € : visite et atelier" if mode in ("don", "mixte") else None,
            deadline=deadline.date().isoformat(), status=status, palette=i,
            jobs_target=jobs, beneficiaries_target=ben, co2_target=co2, odd=odd,
            business_plan=int(i % 5 != 3), legal_entity=int(i % 4 != 2), esg_charter=int(i % 3 != 1),
            impact_report=int(i % 6 != 5), team_size=1 + i % 4, founder_age=age,
            created_at=created.isoformat(timespec="seconds"),
            funded_at=(created + timedelta(days=rnd.randint(25, 55))).isoformat(timespec="seconds") if status == "finance" else None,
        )
        pid = create_project(owner, data)

        # Contributions réparties dans le temps
        target = goal * prog
        raised = 0.0
        end = min(base, datetime.fromisoformat(data["funded_at"]) if data["funded_at"] else base)
        span = max(1, (end - created).days)
        kinds = {"don": ["don"], "pret": ["pret"], "equity": ["equity"], "mixte": ["don", "equity"]}[mode]
        while raised < target:
            kind = rnd.choice(kinds)
            ticket = rnd.choice([20, 50, 100, 150, 300, 500]) if kind == "don" else rnd.choice([500, 1000, 2000, 3000, 4500])
            ticket = min(ticket, max(10, target - raised)) if target - raised < ticket else ticket
            inv = rnd.choice(investors if kind != "don" else investors[:3] + investors[4:])
            if kind != "don" and inv in (investors[3], investors[4]):
                inv = investors[0]
            when = created + timedelta(days=rnd.randint(0, span), hours=rnd.randint(0, 23))
            add_contribution(pid, inv, round(ticket, 2), kind, created_at=when.isoformat(timespec="seconds"))
            raised += ticket

        # Impact constaté pour les projets financés
        if status == "finance":
            for k in range(rnd.randint(2, 3)):
                f = (k + 1) / 3
                add_update(pid, ["Lancement réussi 🎉", "Premiers résultats", "Bilan à 6 mois"][k],
                           "Merci à tous nos contributeurs ! Voici où nous en sommes et ce que votre soutien a permis.",
                           jobs=max(1, int(jobs * f / 2)), benef=int(ben * f / 2), co2=round(co2 * f / 2, 1),
                           revenue=round(goal * rnd.uniform(0.2, 0.6), 0),
                           created_at=(datetime.fromisoformat(data["funded_at"]) + timedelta(days=30 * (k + 1))).isoformat(timespec="seconds"))

        # Questions publiques
        if status in ("en_cours", "finance"):
            q_author = rnd.choice(investors)
            t = created + timedelta(days=5)
            add_comment(pid, q_author, rnd.choice([
                "Quel est votre plan pour atteindre le point mort ?",
                "Comment mesurez-vous concrètement votre impact ?",
                "Avez-vous déjà des partenaires locaux engagés ?",
            ]), created_at=t.isoformat(timespec="seconds"))
            add_comment(pid, owner, "Merci pour la question ! Tout est détaillé dans notre business plan, et nous publierons un rapport d'impact trimestriel.",
                        created_at=(t + timedelta(hours=6)).isoformat(timespec="seconds"))

    # Messagerie privée de démonstration
    t = base - timedelta(days=3)
    send_message(investors[0], porteurs[6 % len(porteurs)], "Bonjour, votre projet m'intéresse. Pouvez-vous partager vos prévisions de chiffre d'affaires sur 3 ans ?", project_id=7, created_at=t.isoformat(timespec="seconds"), is_read=1)
    send_message(porteurs[6 % len(porteurs)], investors[0], "Bonjour Paul, avec plaisir ! Je vous envoie le prévisionnel et je suis disponible pour un appel jeudi.", project_id=7, created_at=(t + timedelta(hours=3)).isoformat(timespec="seconds"))
    send_message(investors[1], porteurs[0], "Félicitations pour la levée. Nous aimerions discuter d'un second tour l'an prochain.", project_id=1, created_at=(base - timedelta(days=1)).isoformat(timespec="seconds"))

    save_prefs(investors[0], {"sectors": ["Éducation", "Santé & Bien-être", "Numérique & Tech"], "regions": [],
                              "modes": ["equity"], "odd": [4, 3, 10], "max_ticket": 5000})
    save_prefs(investors[2], {"sectors": ["AgriTech & Alimentation", "Économie sociale & solidaire"],
                              "regions": ["Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte"],
                              "modes": ["don"], "odd": [2, 6, 12], "max_ticket": 300})
