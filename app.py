"""ÉLAN — Plateforme de financement de l'entrepreneuriat des jeunes.

Lancement :  streamlit run app.py
"""
from __future__ import annotations

import base64
import html
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import db

st.set_page_config(page_title="ÉLAN · Financer les jeunes entrepreneurs", page_icon="🚀", layout="wide")
db.init_db()

ACCENT = "#0f766e"
CHART_COLORS = ["#0f766e", "#f59e0b", "#6366f1", "#e11d48", "#0ea5e9", "#84cc16", "#a855f7", "#f97316", "#14b8a6", "#64748b", "#ec4899"]
px.defaults.color_discrete_sequence = CHART_COLORS


# --------------------------------------------------------------------------
# Style
# --------------------------------------------------------------------------
st.markdown(
    """
<style>
:root { --accent:#0f766e; --muted:#64748b; --card:#ffffff; --line:#e2e8f0; }
.block-container { padding-top: 1.6rem; max-width: 1280px; }
.hero { background: linear-gradient(120deg,#0f766e 0%,#115e59 45%,#f59e0b 140%); color:#fff;
        border-radius: 22px; padding: 2.2rem 2.4rem; margin-bottom: 1.4rem; }
.hero h1 { color:#fff; font-size: 2.3rem; margin: 0 0 .4rem 0; line-height:1.15; }
.hero p { font-size: 1.08rem; opacity:.92; margin:0; max-width: 760px; }
.kpi { background: var(--card); border:1px solid var(--line); border-radius: 16px; padding: 1rem 1.1rem; }
.kpi .v { font-size: 1.6rem; font-weight: 800; color:#0f172a; }
.kpi .l { font-size: .82rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.card { background: var(--card); border:1px solid var(--line); border-radius: 18px; overflow:hidden;
        box-shadow: 0 1px 2px rgba(15,23,42,.04); margin-bottom: .6rem; }
.card img { width:100%; aspect-ratio: 16/9; object-fit: cover; display:block; }
.card .body { padding: .85rem 1rem 1rem 1rem; }
.card h4 { margin: .1rem 0 .2rem 0; font-size: 1.08rem; color:#0f172a; }
.card .tag { color: var(--muted); font-size: .88rem; min-height: 2.6em; }
.pill { display:inline-block; padding: .14rem .55rem; border-radius: 999px; font-size: .74rem; font-weight:600;
        background:#f1f5f9; color:#334155; margin: 0 .25rem .25rem 0; }
.pill.green { background:#ccfbf1; color:#115e59; } .pill.amber { background:#fef3c7; color:#92400e; }
.pill.red { background:#ffe4e6; color:#9f1239; } .pill.blue { background:#e0e7ff; color:#3730a3; }
.bar { height: 8px; background:#e2e8f0; border-radius: 99px; overflow:hidden; margin:.55rem 0 .3rem 0; }
.bar > div { height:100%; background: linear-gradient(90deg,#0f766e,#14b8a6); border-radius: 99px; }
.bar.over > div { background: linear-gradient(90deg,#f59e0b,#fbbf24); }
.meta { display:flex; justify-content: space-between; font-size:.83rem; color:#334155; }
.meta b { color:#0f172a; }
.score { font-size:.78rem; color: var(--muted); margin-top:.35rem; }
.msg { padding:.6rem .85rem; border-radius: 14px; margin:.3rem 0; max-width: 78%; font-size:.94rem; }
.msg.me { background:#ccfbf1; margin-left:auto; } .msg.them { background:#f1f5f9; }
.msg small { display:block; color:#64748b; font-size:.72rem; margin-top:.2rem; }
.crit-ok { color:#15803d; } .crit-ko { color:#b91c1c; }
.disclaimer { font-size:.78rem; color:#64748b; border-top:1px solid #e2e8f0; padding-top:.8rem; margin-top:2rem; }
@media (prefers-color-scheme: dark) {
  :root { --card:#0f172a; --line:#1e293b; --muted:#94a3b8; }
  .kpi .v, .card h4, .meta b { color:#f1f5f9; } .meta { color:#cbd5e1; }
  .pill { background:#1e293b; color:#cbd5e1; } .bar { background:#1e293b; }
  .msg.them { background:#1e293b; } .msg.me { background:#134e4a; }
}
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------
def eur(x: float) -> str:
    x = float(x or 0)
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:,.2f} M€".replace(",", " ").replace(".", ",")
    return f"{x:,.0f} €".replace(",", " ")


def num(x) -> str:
    return f"{float(x or 0):,.0f}".replace(",", " ")


def esc(s) -> str:
    return html.escape(str(s or ""))


def kpi(col, value, label):
    col.markdown(f"<div class='kpi'><div class='v'>{value}</div><div class='l'>{label}</div></div>", unsafe_allow_html=True)


def user():
    uid = st.session_state.get("uid")
    return db.get_user(uid) if uid else None


def go_to(page: str, **state):
    st.session_state["page"] = page
    for k, v in state.items():
        st.session_state[k] = v
    st.rerun()


def status_pill(status: str) -> str:
    cls = {"en_cours": "blue", "finance": "green", "echoue": "red", "en_revue": "amber", "rejete": "red"}.get(status, "")
    return f"<span class='pill {cls}'>{db.STATUS_LABELS.get(status, status)}</span>"


def project_card(p: dict, show_score: str | None = None, prefix: str = "c"):
    pct = p["pct"]
    over = " over" if pct > 100 else ""
    if p["status"] == "en_cours":
        d = int(p["days_left"]) if pd.notna(p["days_left"]) else 0
        right = f"<span><b>{max(d, 0)}</b> j restants</span>"
    elif p["status"] == "finance":
        right = f"<span>👥 <b>{num(p['jobs_done'] or p['jobs_target'])}</b> emplois</span>"
    else:
        right = "<span>Clôturé</span>"
    score_html = ""
    if show_score:
        score_html = f"<div class='score'>{show_score}</div>"
    st.markdown(
        f"""<div class='card'><img src='{db.image_uri(p)}' alt=''/>
<div class='body'>
<div>{status_pill(p['status'])}<span class='pill'>{db.SECTORS.get(p['sector'], '')} {esc(p['sector'])}</span>
<span class='pill'>📍 {esc(p['region'])}</span></div>
<h4>{esc(p['title'])}</h4><div class='tag'>{esc(p['tagline'])}</div>
<div class='bar{over}'><div style='width:{min(pct, 100):.0f}%'></div></div>
<div class='meta'><span><b>{eur(p['raised'])}</b> / {eur(p['goal'])} · {pct:.0f} %</span>{right}</div>
{score_html}</div></div>""",
        unsafe_allow_html=True,
    )
    if st.button("Voir le projet →", key=f"see_{prefix}_{p['id']}", width="stretch"):
        go_to("Fiche projet", project_id=int(p["id"]))


def card_grid(df: pd.DataFrame, cols: int = 3, score_fn=None, prefix: str = "g"):
    rows = [df.iloc[i:i + cols] for i in range(0, len(df), cols)]
    for chunk in rows:
        cs = st.columns(cols)
        for c, (_, p) in zip(cs, chunk.iterrows()):
            with c:
                project_card(p.to_dict(), score_fn(p) if score_fn else None, prefix)


def plot_style(fig, h=340):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(size=12), legend=dict(orientation="h", y=-0.15),
                      colorway=CHART_COLORS)
    return fig


# --------------------------------------------------------------------------
# Barre latérale : navigation & connexion
# --------------------------------------------------------------------------
u = user()
PAGES = ["Accueil", "Explorer les projets", "Projets financés", "Statistiques", "Messagerie",
         "Soumettre un projet", "Mon espace", "Administration"]
ICONS = {"Accueil": "🏠", "Explorer les projets": "🔎", "Projets financés": "🏆", "Statistiques": "📊",
         "Messagerie": "💬", "Soumettre un projet": "🚀", "Mon espace": "👤", "Administration": "🛡️", "Fiche projet": "📄"}

with st.sidebar:
    st.markdown("## 🚀 ÉLAN")
    st.caption("Financer l'audace des jeunes entrepreneurs")
    visible = [p for p in PAGES if not (p == "Administration" and (not u or u["role"] != "admin"))]
    current = st.session_state.get("page", "Accueil")
    labels = []
    for p in visible:
        lab = f"{ICONS[p]} {p}"
        if p == "Messagerie" and u:
            n = db.unread_count(u["id"])
            if n:
                lab += f"  ({n})"
        labels.append(lab)
    idx = visible.index(current) if current in visible else None
    choice = st.radio("Navigation", labels, index=idx, label_visibility="collapsed", key=f"nav_{current}")
    if choice:
        chosen = visible[labels.index(choice)]
        if chosen != current:
            go_to(chosen)

    st.divider()
    if u:
        role_lbl = {"porteur": "Porteur·se de projet", "investisseur": "Investisseur·se / contributeur·rice", "admin": "Administrateur"}[u["role"]]
        kyc = {"verifie": "✅ Identité vérifiée", "en_cours": "⏳ KYC en cours", "non_verifie": "⚠️ Identité non vérifiée"}[u["kyc_status"]]
        st.markdown(f"**{esc(u['name'])}**  \n{role_lbl}  \n{kyc}")
        if st.button("Se déconnecter", width="stretch"):
            st.session_state.pop("uid", None)
            go_to("Accueil")
    else:
        tab_in, tab_up = st.tabs(["Connexion", "Inscription"])
        with tab_in:
            with st.form("login"):
                email = st.text_input("E-mail")
                pwd = st.text_input("Mot de passe", type="password")
                if st.form_submit_button("Se connecter", width="stretch"):
                    found = db.authenticate(email, pwd)
                    if found:
                        st.session_state["uid"] = found["id"]
                        st.rerun()
                    st.error("Identifiants incorrects.")
            with st.expander("Comptes de démonstration"):
                st.caption(f"Mot de passe commun : `{db.DEMO_PASSWORD}`")
                st.code("porteur1@elan.fr\ninvestisseur1@elan.fr\nadmin@elan.fr", language=None)
        with tab_up:
            with st.form("signup"):
                name = st.text_input("Nom complet")
                email2 = st.text_input("E-mail ")
                pwd2 = st.text_input("Mot de passe (8 caractères min.)", type="password")
                role = st.radio("Je suis", ["porteur", "investisseur"],
                                format_func=lambda r: "Porteur·se de projet" if r == "porteur" else "Investisseur·se / contributeur·rice")
                by = st.number_input("Année de naissance", 1940, date.today().year - 16, 2000)
                city = st.text_input("Ville")
                ok = st.checkbox("J'accepte les conditions d'utilisation")
                if st.form_submit_button("Créer mon compte", width="stretch"):
                    if not (name and "@" in email2 and len(pwd2) >= 8 and ok):
                        st.error("Complétez tous les champs (mot de passe ≥ 8 caractères) et acceptez les conditions.")
                    else:
                        try:
                            st.session_state["uid"] = db.create_user(email2, name, pwd2, role, birth_year=int(by), city=city)
                            st.rerun()
                        except Exception:
                            st.error("Cet e-mail est déjà utilisé.")

page = st.session_state.get("page", "Accueil")
all_df = db.projects_df()
contrib_df = db.contributions_df()
confirmed = contrib_df[contrib_df["status"] == "confirme"] if not contrib_df.empty else contrib_df


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_home():
    st.markdown(
        """<div class='hero'><h1>Donnons de l'élan aux projets des jeunes.</h1>
<p>Soutenez par le don, prêtez ou investissez au capital de projets portés par des entrepreneurs de moins de 30 ans,
en métropole et dans les Outre-mer. Chaque euro est suivi, chaque impact est mesuré.</p></div>""",
        unsafe_allow_html=True,
    )
    funded = all_df[all_df["status"] == "finance"]
    closed = all_df[all_df["status"].isin(["finance", "echoue"])]
    c = st.columns(5)
    kpi(c[0], eur(confirmed["amount"].sum() if not confirmed.empty else 0), "Collectés")
    kpi(c[1], num(len(funded)), "Projets financés")
    kpi(c[2], f"{(len(funded) / len(closed) * 100 if len(closed) else 0):.0f} %", "Taux de réussite")
    kpi(c[3], num(funded["jobs_done"].sum()), "Emplois créés")
    kpi(c[4], num(confirmed["user_id"].nunique() if not confirmed.empty else 0), "Contributeurs")

    st.markdown("### 🏆 Ils ont réussi leur levée")
    card_grid(funded.sort_values("funded_at", ascending=False).head(3), prefix="home_f")

    st.markdown("### 🔥 En collecte — bientôt financés")
    live = all_df[all_df["status"] == "en_cours"].sort_values("pct", ascending=False).head(3)
    card_grid(live, prefix="home_l")

    st.markdown("### Comment ça marche ?")
    a, b, c3, d = st.columns(4)
    a.markdown("**1. Déposer**  \nLe porteur soumet son projet, ses objectifs d'impact et ses justificatifs.")
    b.markdown("**2. Vérifier**  \nL'équipe ÉLAN contrôle l'identité (KYC), les critères et valide la mise en ligne.")
    c3.markdown("**3. Financer**  \nDon, prêt ou capital : chacun choisit sa façon de soutenir, selon ses préférences.")
    d.markdown("**4. Mesurer**  \nLe porteur publie ses résultats : emplois, bénéficiaires, CO₂ évité.")


def filters_and_ranking(df: pd.DataFrame, prefs: dict):
    with st.expander("🎯 Filtres, préférences et critères", expanded=True):
        c1, c2, c3 = st.columns(3)
        q = c1.text_input("Recherche", placeholder="Mot-clé, nom de projet…")
        sectors = c1.multiselect("Secteurs", list(db.SECTORS), default=prefs.get("sectors", []))
        regions = c2.multiselect("Territoires", db.REGIONS, default=prefs.get("regions", []))
        modes = c2.multiselect("Mode de financement", list(db.MODES), format_func=db.MODES.get, default=prefs.get("modes", []))
        odd = c3.multiselect("Objectifs de développement durable (ODD)", list(db.ODD),
                             format_func=lambda k: f"ODD {k} · {db.ODD[k]}", default=prefs.get("odd", []))
        statuses = c3.multiselect("Statut", ["en_cours", "finance", "echoue"], default=["en_cours"],
                                  format_func=db.STATUS_LABELS.get)
        c4, c5, c6 = st.columns(3)
        required = c4.multiselect("Critères obligatoires", [k for k, _, _ in db.CRITERIA],
                                  format_func=db.CRITERIA_LABELS.get,
                                  help="N'afficher que les projets qui respectent tous les critères cochés.")
        min_crit = c5.slider("Score de critères minimum", 0, 100, 0, 5)
        max_ticket = c6.number_input("Mon ticket max (€)", 0, 1_000_000, int(prefs.get("max_ticket", 0) or 0), 50,
                                     help="0 = pas de limite. Exclut les projets dont le ticket minimum est supérieur.")
        sort = st.radio("Classer par", ["Adéquation à mes préférences", "Score de critères", "Score d'impact",
                                        "Taux de financement", "Fin de collecte la plus proche", "Plus récents", "Montant levé"],
                        horizontal=True)

    f = df.copy()
    if q:
        m = f["title"].str.contains(q, case=False) | f["tagline"].str.contains(q, case=False) | f["description"].str.contains(q, case=False)
        f = f[m]
    if statuses:
        f = f[f["status"].isin(statuses)]
    if sectors:
        f = f[f["sector"].isin(sectors)]
    if regions:
        f = f[f["region"].isin(regions)]
    if modes:
        f = f[f["mode"].isin(modes) | ((f["mode"] == "mixte") & bool(set(modes) & {"don", "equity"}))]
    if odd:
        f = f[f["odd_list"].apply(lambda l: bool(set(l) & set(odd)))]
    if required:
        f = f[f["criteria"].apply(lambda c: all(c.get(k) for k in required))]
    f = f[f["criteria_score"] >= min_crit]
    if max_ticket:
        f = f[f["min_ticket"].fillna(0) <= max_ticket]

    active = {"sectors": sectors, "regions": regions, "modes": modes, "odd": odd, "max_ticket": max_ticket}
    if not f.empty:
        f["match"] = f.apply(lambda p: db.match_score(p, active if any(active.values()) else prefs), axis=1)
    key = {"Adéquation à mes préférences": ("match", False), "Score de critères": ("criteria_score", False),
           "Score d'impact": ("impact_score", False), "Taux de financement": ("pct", False),
           "Fin de collecte la plus proche": ("days_left", True), "Plus récents": ("created_at", False),
           "Montant levé": ("raised", False)}[sort]
    if not f.empty:
        f = f.sort_values(key[0], ascending=key[1])
    return f, active, sort


def page_explore():
    st.title("🔎 Explorer les projets")
    prefs = db.get_prefs(u["id"]) if u else {}
    if u and u["role"] == "investisseur" and prefs:
        st.caption("Vos préférences enregistrées sont pré-remplies. Modifiez-les dans « Mon espace ».")
    f, active, sort = filters_and_ranking(all_df, prefs)
    favs = db.favorites(u["id"]) if u else set()

    left, right = st.columns([3, 1])
    left.markdown(f"**{len(f)} projet(s)** correspondent à votre recherche.")
    view = right.radio("Affichage", ["Cartes", "Tableau"], horizontal=True, label_visibility="collapsed")
    if f.empty:
        st.info("Aucun projet ne correspond. Élargissez vos filtres.")
        return
    if view == "Tableau":
        t = f[["title", "sector", "region", "mode", "goal", "raised", "pct", "match", "criteria_score", "impact_score", "days_left"]].copy()
        t["mode"] = t["mode"].map(db.MODES)
        t.columns = ["Projet", "Secteur", "Territoire", "Mode", "Objectif €", "Levé €", "Avancement %", "Adéquation",
                     "Critères", "Impact", "Jours restants"]
        st.dataframe(t, hide_index=True, width="stretch",
                     column_config={"Avancement %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                                    "Adéquation": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
                                    "Critères": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
                                    "Impact": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
                                    "Objectif €": st.column_config.NumberColumn(format="%d"),
                                    "Levé €": st.column_config.NumberColumn(format="%d")})
        pick = st.selectbox("Ouvrir un projet", f["title"].tolist(), index=None, placeholder="Choisir…")
        if pick:
            go_to("Fiche projet", project_id=int(f[f["title"] == pick]["id"].iloc[0]))
        return

    def score_line(p):
        star = "⭐ " if p["id"] in favs else ""
        return f"{star}Adéquation <b>{p['match']:.0f}</b>/100 · Critères <b>{p['criteria_score']:.0f}</b> · Impact <b>{p['impact_score']:.0f}</b>"

    card_grid(f, 3, score_line, prefix="exp")


def page_project():
    pid = st.session_state.get("project_id")
    p = db.get_project(pid) if pid else None
    if not p:
        st.warning("Projet introuvable.")
        return
    is_owner = u and u["id"] == p["owner_id"]
    is_admin = u and u["role"] == "admin"
    if p["status"] in ("en_revue", "rejete") and not (is_owner or is_admin):
        st.warning("Ce projet n'est pas encore publié.")
        return
    if st.button("← Retour aux projets"):
        go_to("Explorer les projets")

    top_l, top_r = st.columns([1.6, 1])
    with top_l:
        st.markdown(f"<img src='{db.image_uri(p)}' style='width:100%;border-radius:18px;aspect-ratio:16/9;object-fit:cover'/>",
                    unsafe_allow_html=True)
    with top_r:
        st.markdown(status_pill(p["status"]) + f"<span class='pill'>{db.SECTORS.get(p['sector'], '')} {esc(p['sector'])}</span>"
                    f"<span class='pill'>📍 {esc(p['region'])}</span><span class='pill blue'>{esc(db.MODES[p['mode']])}</span>",
                    unsafe_allow_html=True)
        st.markdown(f"## {esc(p['title'])}")
        st.markdown(f"*{esc(p['tagline'])}*")
        st.caption(f"Porté par **{p['owner_name']}** · {p['founder_age'] or '–'} ans · {p['owner_city'] or ''} · équipe de {p['team_size']}")
        pct = p["pct"]
        st.progress(min(pct / 100, 1.0), text=f"{eur(p['raised'])} collectés sur {eur(p['goal'])} ({pct:.0f} %)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Contributeurs", num(p["backers"]))
        m2.metric("Jours restants" if p["status"] == "en_cours" else "Statut",
                  max(int(p["days_left"]), 0) if p["status"] == "en_cours" else db.STATUS_LABELS[p["status"]])
        m3.metric("Ticket min.", eur(p["min_ticket"]))
        if p["mode"] in ("equity", "mixte") and p["valuation"]:
            st.caption(f"Valorisation pré-money : **{eur(p['valuation'])}** · Part ouverte : **{p['equity_pct']:.1f} %** du capital")
        if p["mode"] == "pret" and p["interest_rate"]:
            st.caption(f"Taux : **{p['interest_rate']:.1f} %** / an · Durée : **{p['duration_months']} mois**")
        if u and u["role"] != "admin":
            favs = db.favorites(u["id"])
            if st.button("★ Retirer des favoris" if pid in favs else "☆ Ajouter aux favoris", width="stretch"):
                db.toggle_favorite(u["id"], pid)
                st.rerun()

    tabs = st.tabs(["📖 Le projet", "💶 Financer", "🌍 Impact", "✅ Critères", "📰 Actualités", "💬 Échanges", "👥 Contributeurs"])

    with tabs[0]:
        st.markdown(p["description"] or "")
        if p["rewards"]:
            st.markdown("**Contreparties**")
            for r in str(p["rewards"]).split("·"):
                st.markdown(f"- {r.strip()}")
        if p["odd_list"]:
            st.markdown("**Objectifs de développement durable visés**")
            st.markdown("".join(f"<span class='pill green'>ODD {k} · {db.ODD[k]}</span>" for k in p["odd_list"]), unsafe_allow_html=True)

    with tabs[1]:
        if p["status"] != "en_cours":
            st.info("La collecte de ce projet est clôturée.")
        elif not u:
            st.info("Connectez-vous ou créez un compte pour soutenir ce projet.")
        elif u["role"] == "admin":
            st.info("Les administrateurs ne peuvent pas contribuer.")
        else:
            kinds = {"don": ["don"], "pret": ["pret"], "equity": ["equity"], "mixte": ["don", "equity"]}[p["mode"]]
            labels = {"don": "🎁 Don avec contrepartie", "pret": "🏦 Prêt rémunéré", "equity": "📈 Investissement au capital"}
            with st.form("contrib"):
                kind = st.radio("Je souhaite", kinds, format_func=labels.get, horizontal=True)
                amount = st.number_input("Montant (€)", min_value=float(p["min_ticket"] or 1), value=float(max(p["min_ticket"] or 10, 50)), step=10.0)
                if kind == "equity" and p["valuation"]:
                    st.caption(f"Votre part estimée : {amount / (p['valuation'] + p['goal']) * 100:.3f} % du capital post-money.")
                if kind == "pret" and p["interest_rate"]:
                    total = amount * (1 + p["interest_rate"] / 100 * (p["duration_months"] or 36) / 12)
                    st.caption(f"Remboursement estimé (intérêts simples) : {eur(total)} sur {p['duration_months']} mois.")
                risk = st.checkbox("J'ai compris les risques (perte en capital, illiquidité, défaut de remboursement)." if kind != "don"
                                   else "Je comprends qu'un don n'est pas remboursable.")
                if st.form_submit_button("Confirmer ma contribution", type="primary"):
                    allowed, err, alert = db.check_contribution(u, p, amount, kind)
                    if not risk:
                        st.error("Merci de confirmer avoir pris connaissance des risques.")
                    elif not allowed:
                        st.error(err)
                    else:
                        db.add_contribution(pid, u["id"], amount, kind, alert=alert)
                        if alert:
                            st.warning("Contribution enregistrée et placée en revue par l'équipe conformité avant validation.")
                        else:
                            st.success(f"Merci ! Votre contribution de {eur(amount)} est confirmée. 🎉")
                            st.balloons()
            st.caption("Paiement simulé (démonstration). En production : prestataire de paiement agréé et compte de cantonnement.")

    with tabs[2]:
        rows = [("Emplois créés", p["jobs_target"], p["jobs_done"], ""), ("Bénéficiaires", p["beneficiaries_target"], p["benef_done"], ""),
                ("CO₂ évité", p["co2_target"], p["co2_done"], " t")]
        cs = st.columns(3)
        for c, (lbl, tgt, done, unit) in zip(cs, rows):
            c.metric(lbl, f"{num(done)}{unit}", f"objectif {num(tgt)}{unit}", delta_color="off")
            if tgt:
                c.progress(min(done / tgt, 1.0))
        st.metric("Score d'impact", f"{p['impact_score']:.0f} / 100")
        ups = db.updates(pid)
        if ups:
            h = pd.DataFrame(ups).sort_values("created_at")
            h["Emplois (cumul)"] = h["jobs_created"].cumsum()
            h["Bénéficiaires (cumul)"] = h["beneficiaries"].cumsum()
            h["Date"] = pd.to_datetime(h["created_at"]).dt.date
            fig = px.line(h, x="Date", y=["Emplois (cumul)", "Bénéficiaires (cumul)"], markers=True, title="Impact constaté dans le temps")
            st.plotly_chart(plot_style(fig), width="stretch")
        else:
            st.caption("L'impact réalisé sera publié par le porteur après le financement.")

    with tabs[3]:
        st.markdown(f"### Score de critères : {p['criteria_score']:.0f} / 100")
        for k, lbl, w in db.CRITERIA:
            ok = p["criteria"][k]
            st.markdown(f"<span class='{'crit-ok' if ok else 'crit-ko'}'>{'✔' if ok else '✘'}</span> {lbl} <span style='color:#64748b'>({w} pts)</span>",
                        unsafe_allow_html=True)

    with tabs[4]:
        ups = db.updates(pid)
        if not ups:
            st.caption("Pas encore d'actualité.")
        for x in ups:
            with st.container(border=True):
                st.markdown(f"**{esc(x['title'])}** · {x['created_at'][:10]}")
                st.write(x["body"])
                st.caption(f"+{x['jobs_created']} emplois · +{num(x['beneficiaries'])} bénéficiaires · {x['co2_avoided']} t CO₂ évitées · CA {eur(x['revenue'])}")

    with tabs[5]:
        st.markdown("#### Questions publiques")
        for cmt in db.comments(pid):
            badge = " · 🚀 Porteur" if cmt["user_id"] == p["owner_id"] else (" · 🛡️ ÉLAN" if cmt["role"] == "admin" else "")
            with st.chat_message("assistant" if cmt["user_id"] == p["owner_id"] else "user"):
                st.markdown(f"**{esc(cmt['name'])}**{badge} · <small>{cmt['created_at'][:16].replace('T', ' ')}</small>", unsafe_allow_html=True)
                st.write(cmt["body"])
        if u:
            with st.form("comment", clear_on_submit=True):
                body = st.text_area("Poser une question ou répondre publiquement", height=80)
                if st.form_submit_button("Publier") and body.strip():
                    db.add_comment(pid, u["id"], body)
                    st.rerun()
            if not is_owner:
                st.markdown("#### Message privé au porteur")
                with st.form("pm", clear_on_submit=True):
                    body = st.text_area("Votre message (visible uniquement par le porteur)", height=80)
                    if st.form_submit_button("Envoyer") and body.strip():
                        db.send_message(u["id"], p["owner_id"], body, project_id=pid)
                        st.success("Message envoyé. Retrouvez la conversation dans « Messagerie ».")
        else:
            st.info("Connectez-vous pour échanger avec le porteur.")

    with tabs[6]:
        cl = db.contributors(pid)
        if not cl:
            st.caption("Aucun contributeur pour le moment.")
        else:
            t = pd.DataFrame(cl)
            if not (is_owner or is_admin):
                t["name"] = t["name"].apply(lambda n: n.split()[0] + " " + (n.split()[1][0] + "." if len(n.split()) > 1 else ""))
            t = t.rename(columns={"name": "Contributeur", "total": "Montant €", "kinds": "Type", "last": "Dernière contribution"})
            st.dataframe(t[["Contributeur", "Montant €", "Type", "Dernière contribution"]], hide_index=True, width="stretch")
            if is_owner:
                st.caption("Vous voyez les noms complets en tant que porteur. Les visiteurs voient des noms abrégés.")


def page_funded():
    st.title("🏆 Projets financés")
    st.caption("La vitrine des projets qui ont atteint leur objectif, et de l'impact qu'ils génèrent.")
    f = all_df[all_df["status"] == "finance"].copy()
    if f.empty:
        st.info("Aucun projet financé pour le moment.")
        return
    c = st.columns(5)
    kpi(c[0], num(len(f)), "Projets financés")
    kpi(c[1], eur(f["raised"].sum()), "Montant levé")
    kpi(c[2], num(f["jobs_done"].sum()), "Emplois créés")
    kpi(c[3], num(f["benef_done"].sum()), "Bénéficiaires")
    kpi(c[4], f"{num(f['co2_done'].sum())} t", "CO₂ évité")
    st.write("")
    s1, s2 = st.columns([2, 1])
    sec = s1.multiselect("Secteur", sorted(f["sector"].unique()))
    order = s2.selectbox("Trier par", ["Impact", "Montant levé", "Plus récents", "Sur-financement"])
    if sec:
        f = f[f["sector"].isin(sec)]
    f = f.sort_values({"Impact": "impact_score", "Montant levé": "raised", "Plus récents": "funded_at", "Sur-financement": "pct"}[order], ascending=False)

    for _, p in f.iterrows():
        with st.container(border=True):
            a, b, c2 = st.columns([1.2, 2, 1.2])
            a.markdown(f"<img src='{db.image_uri(p)}' style='width:100%;border-radius:14px;aspect-ratio:16/9;object-fit:cover'/>", unsafe_allow_html=True)
            with b:
                st.markdown(f"### {esc(p['title'])}")
                st.markdown(f"<span class='pill'>{db.SECTORS.get(p['sector'], '')} {esc(p['sector'])}</span><span class='pill'>📍 {esc(p['region'])}</span>"
                            f"<span class='pill blue'>{esc(db.MODES[p['mode']])}</span>", unsafe_allow_html=True)
                st.write(p["tagline"])
                st.caption(f"Financé le {str(p['funded_at'])[:10]} · {num(p['backers'])} contributeurs · {p['pct']:.0f} % de l'objectif")
                if st.button("Voir la fiche", key=f"funded_{p['id']}"):
                    go_to("Fiche projet", project_id=int(p["id"]))
            with c2:
                st.metric("Levé", eur(p["raised"]))
                st.metric("Emplois créés", num(p["jobs_done"]), f"objectif {num(p['jobs_target'])}", delta_color="off")
                st.metric("Bénéficiaires", num(p["benef_done"]))


def page_stats():
    st.title("📊 Statistiques de la plateforme")
    if confirmed.empty:
        st.info("Pas encore de données.")
        return
    df = all_df
    closed = df[df["status"].isin(["finance", "echoue"])]
    funded = df[df["status"] == "finance"]
    c = st.columns(6)
    kpi(c[0], eur(confirmed["amount"].sum()), "Total collecté")
    kpi(c[1], num(len(df)), "Projets publiés")
    kpi(c[2], f"{(len(funded) / len(closed) * 100 if len(closed) else 0):.0f} %", "Taux de réussite")
    kpi(c[3], eur(confirmed["amount"].mean()), "Ticket moyen")
    kpi(c[4], num(confirmed["user_id"].nunique()), "Contributeurs")
    kpi(c[5], f"{df['founder_age'].mean():.0f} ans", "Âge moyen porteurs")
    st.write("")

    t1, t2, t3, t4 = st.tabs(["💶 Collecte", "🗺️ Secteurs & territoires", "🌍 Impact", "🏅 Classements"])
    with t1:
        m = confirmed.set_index("created_at").resample("ME")["amount"].sum().reset_index()
        m["Cumul"] = m["amount"].cumsum()
        fig = go.Figure()
        fig.add_bar(x=m["created_at"], y=m["amount"], name="Collecte mensuelle", marker_color=ACCENT)
        fig.add_scatter(x=m["created_at"], y=m["Cumul"], name="Cumul", yaxis="y2", line=dict(color="#f59e0b", width=3))
        fig.update_layout(title="Collecte mensuelle et cumulée (€)", yaxis2=dict(overlaying="y", side="right", showgrid=False))
        st.plotly_chart(plot_style(fig, 380), width="stretch")
        a, b = st.columns(2)
        bykind = confirmed.groupby("kind")["amount"].sum().rename({"don": "Don", "pret": "Prêt", "equity": "Capital"}).reset_index()
        a.plotly_chart(plot_style(px.pie(bykind, names="kind", values="amount", hole=.55, title="Répartition par mode de financement")), width="stretch")
        st_counts = df["status"].map(db.STATUS_LABELS).value_counts().reset_index()
        st_counts.columns = ["Statut", "Projets"]
        b.plotly_chart(plot_style(px.bar(st_counts, x="Statut", y="Projets", title="Projets par statut", color="Statut", color_discrete_map={"En collecte": "#6366f1", "Financé": "#0f766e", "Objectif non atteint": "#e11d48", "En revue": "#f59e0b"})), width="stretch")
        hist = px.histogram(confirmed, x="amount", nbins=30, title="Distribution des tickets (€)", labels={"amount": "Montant du ticket (€)"})
        hist.update_layout(yaxis_title="Nombre de contributions")
        st.plotly_chart(plot_style(hist, 300), width="stretch")
    with t2:
        a, b = st.columns(2)
        s = df.groupby("sector").agg(Levé=("raised", "sum"), Projets=("id", "count")).reset_index().sort_values("Levé")
        a.plotly_chart(plot_style(px.bar(s, x="Levé", y="sector", orientation="h", title="Montant levé par secteur (€)", text="Projets"), 420), width="stretch")
        r = df.groupby("region").agg(Levé=("raised", "sum"), Projets=("id", "count")).reset_index().sort_values("Levé")
        b.plotly_chart(plot_style(px.bar(r, x="Levé", y="region", orientation="h", title="Montant levé par territoire (€)", text="Projets"), 420), width="stretch")
        sr = closed.groupby("sector").apply(lambda g: (g["status"] == "finance").mean() * 100, include_groups=False).reset_index(name="Taux de réussite %")
        if not sr.empty:
            st.plotly_chart(plot_style(px.bar(sr, x="sector", y="Taux de réussite %", title="Taux de réussite des collectes clôturées par secteur")), width="stretch")
    with t3:
        c = st.columns(3)
        kpi(c[0], num(df["jobs_done"].sum()), "Emplois créés (constatés)")
        kpi(c[1], num(df["benef_done"].sum()), "Bénéficiaires touchés")
        kpi(c[2], f"{num(df['co2_done'].sum())} t", "CO₂ évité")
        odd_counts = pd.Series([k for l in df["odd_list"] for k in l]).value_counts().reset_index()
        odd_counts.columns = ["odd", "Projets"]
        odd_counts["ODD"] = odd_counts["odd"].apply(lambda k: f"ODD {k} · {db.ODD[k]}")
        st.plotly_chart(plot_style(px.bar(odd_counts.sort_values("Projets"), x="Projets", y="ODD", orientation="h", title="Contribution aux ODD (nombre de projets)"), 460), width="stretch")
        sc = px.scatter(df, x="criteria_score", y="impact_score", size="goal", color="sector", hover_name="title",
                        title="Qualité (critères) vs impact — taille = objectif de collecte",
                        labels={"criteria_score": "Score de critères", "impact_score": "Score d'impact"})
        st.plotly_chart(plot_style(sc, 460), width="stretch")
    with t4:
        a, b = st.columns(2)
        a.markdown("**Top 5 — montant levé**")
        a.dataframe(df.nlargest(5, "raised")[["title", "raised", "backers"]].rename(columns={"title": "Projet", "raised": "Levé €", "backers": "Contributeurs"}), hide_index=True, width="stretch")
        b.markdown("**Top 5 — score d'impact**")
        b.dataframe(df.nlargest(5, "impact_score")[["title", "impact_score", "sector"]].rename(columns={"title": "Projet", "impact_score": "Impact", "sector": "Secteur"}), hide_index=True, width="stretch")
        a.markdown("**Top 5 — sur-financement**")
        a.dataframe(df.nlargest(5, "pct")[["title", "pct"]].rename(columns={"title": "Projet", "pct": "% objectif"}).round(0), hide_index=True, width="stretch")
        b.markdown("**Top 5 — score de critères**")
        b.dataframe(df.nlargest(5, "criteria_score")[["title", "criteria_score"]].rename(columns={"title": "Projet", "criteria_score": "Critères"}), hide_index=True, width="stretch")
    st.download_button("⬇️ Exporter les projets (CSV)", df.drop(columns=["image", "criteria", "odd_list", "deadline_dt"]).to_csv(index=False).encode("utf-8-sig"),
                       "elan_projets.csv", "text/csv")


def page_messages():
    st.title("💬 Messagerie")
    if not u:
        st.info("Connectez-vous pour accéder à vos échanges avec les porteurs et investisseurs.")
        return
    convs = db.conversations(u["id"])
    left, right = st.columns([1, 2.2])
    with left:
        st.markdown("**Conversations**")
        if not convs:
            st.caption("Aucune conversation. Contactez un porteur depuis la fiche d'un projet.")
        for i, c in enumerate(convs):
            role = "🚀" if c["other_role"] == "porteur" else ("🛡️" if c["other_role"] == "admin" else "💼")
            unread = f" 🔵 {c['unread']}" if c["unread"] else ""
            if st.button(f"{role} {c['other_name']}{unread}\n\n{c['project_title']}", key=f"conv_{i}", width="stretch"):
                st.session_state["conv"] = (c["other"], c["project_id"])
                st.rerun()
    with right:
        sel = st.session_state.get("conv") or ((convs[0]["other"], convs[0]["project_id"]) if convs else None)
        if not sel:
            return
        other, proj = sel
        o = db.get_user(other)
        title = next((c["project_title"] for c in convs if c["other"] == other and c["project_id"] == proj), "Général")
        with st.container(border=True):
            st.markdown(f"**{esc(o['name'])}** · {title}")
            for m in db.thread(u["id"], other, proj):
                me = m["sender_id"] == u["id"]
                st.markdown(f"<div class='msg {'me' if me else 'them'}'>{esc(m['body'])}<small>{m['created_at'][:16].replace('T', ' ')}</small></div>",
                            unsafe_allow_html=True)
        with st.form("reply", clear_on_submit=True):
            body = st.text_area("Votre réponse", height=90)
            if st.form_submit_button("Envoyer", type="primary") and body.strip():
                db.send_message(u["id"], other, body, project_id=proj)
                st.session_state["conv"] = (other, proj)
                st.rerun()


def page_submit():
    st.title("🚀 Soumettre un projet")
    if not u:
        st.info("Créez un compte « Porteur·se de projet » pour déposer votre projet.")
        return
    if u["role"] != "porteur":
        st.info("Seuls les comptes porteurs peuvent déposer un projet.")
        return
    age = date.today().year - (u["birth_year"] or 2000)
    if age > 30:
        st.warning("ÉLAN est dédié aux porteurs de 30 ans ou moins : votre projet pourra être déposé mais le critère « jeune porteur » ne sera pas rempli.")
    with st.form("new_project"):
        st.markdown("#### 1. Présentation")
        c1, c2 = st.columns(2)
        title = c1.text_input("Nom du projet *")
        tagline = c2.text_input("Accroche (une phrase) *", max_chars=110)
        description = st.text_area("Description détaillée (problème, solution, utilisation des fonds) *", height=170)
        c1, c2, c3 = st.columns(3)
        sector = c1.selectbox("Secteur *", list(db.SECTORS))
        region = c2.selectbox("Territoire *", db.REGIONS)
        team = c3.number_input("Taille de l'équipe", 1, 50, 1)
        image = st.file_uploader("Image de couverture (JPG/PNG, 16:9 conseillé)", type=["jpg", "jpeg", "png", "webp"])

        st.markdown("#### 2. Financement")
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Mode de financement *", list(db.MODES), format_func=db.MODES.get)
        goal = c2.number_input("Objectif de collecte (€) *", 1000, 2_000_000, 20000, 500)
        min_ticket = c3.number_input("Ticket minimum (€)", 5, 50000, 20, 5)
        c1, c2, c3 = st.columns(3)
        deadline = c1.date_input("Date de fin de collecte *", date.today() + timedelta(days=45),
                                 min_value=date.today() + timedelta(days=7), max_value=date.today() + timedelta(days=120))
        valuation = c2.number_input("Valorisation pré-money (€) — capital", 0, 50_000_000, 0, 10000)
        rate = c3.number_input("Taux d'intérêt annuel (%) — prêt", 0.0, 12.0, 0.0, 0.5)
        c1, c2 = st.columns(2)
        duration = c1.number_input("Durée du prêt (mois)", 0, 84, 0, 6)
        rewards = c2.text_input("Contreparties (séparées par ·) — don", placeholder="10 € : merci · 50 € : produit offert")

        st.markdown("#### 3. Impact visé")
        c1, c2, c3 = st.columns(3)
        jobs = c1.number_input("Emplois créés visés", 0, 1000, 0)
        ben = c2.number_input("Bénéficiaires visés", 0, 1_000_000, 0)
        co2 = c3.number_input("CO₂ évité visé (t/an)", 0.0, 100000.0, 0.0)
        odd = st.multiselect("ODD visés", list(db.ODD), format_func=lambda k: f"ODD {k} · {db.ODD[k]}")

        st.markdown("#### 4. Critères & engagements")
        c1, c2 = st.columns(2)
        bp = c1.checkbox("Je fournis un business plan")
        bp_file = c1.file_uploader("Business plan (PDF)", type=["pdf"])
        legal = c2.checkbox("Ma structure est immatriculée (SIREN)")
        esg = c1.checkbox("Je signe la charte ESG / éthique ÉLAN")
        report = c2.checkbox("Je m'engage à publier un reporting d'impact trimestriel")
        cert = st.checkbox("Je certifie l'exactitude des informations et l'origine licite des fonds du projet *")
        submitted = st.form_submit_button("Soumettre pour validation", type="primary")

    if submitted:
        if not (title and tagline and description and cert):
            st.error("Merci de remplir les champs obligatoires (*) et de certifier les informations.")
            return
        if mode in ("equity", "mixte") and not valuation:
            st.error("Indiquez une valorisation pour un financement au capital.")
            return
        if mode == "pret" and not (rate and duration):
            st.error("Indiquez un taux et une durée pour un prêt.")
            return
        img_b64 = mime = None
        if image:
            img_b64 = base64.b64encode(image.getvalue()).decode()
            mime = image.type
        pid = db.create_project(u["id"], dict(
            title=title, tagline=tagline, description=description, sector=sector, region=region, mode=mode,
            goal=goal, min_ticket=min_ticket, deadline=deadline.isoformat(),
            valuation=valuation or None, equity_pct=round(goal / (valuation + goal) * 100, 2) if valuation else None,
            interest_rate=rate or None, duration_months=duration or None, rewards=rewards or None,
            image=img_b64, image_mime=mime, jobs_target=jobs, beneficiaries_target=ben, co2_target=co2,
            odd=",".join(map(str, odd)), business_plan=int(bp or bool(bp_file)), legal_entity=int(legal),
            esg_charter=int(esg), impact_report=int(report), team_size=team, founder_age=age,
        ))
        st.success("Projet soumis ! L'équipe ÉLAN le vérifie avant sa mise en ligne (vous serez notifié dans la messagerie).")
        if st.button("Voir l'aperçu"):
            go_to("Fiche projet", project_id=pid)


def page_me():
    st.title("👤 Mon espace")
    if not u:
        st.info("Connectez-vous pour accéder à votre espace.")
        return

    with st.expander(f"🪪 Vérification d'identité (KYC) — statut : {u['kyc_status'].replace('_', ' ')}", expanded=u["kyc_status"] == "non_verifie"):
        st.caption(f"Obligatoire pour déposer un projet publié, prêter, investir au capital ou dépasser {num(db.KYC_THRESHOLD)} € de contributions cumulées.")
        if u["kyc_status"] == "verifie":
            st.success("Votre identité est vérifiée.")
        elif u["kyc_status"] == "en_cours":
            st.info("Vos justificatifs sont en cours d'analyse par l'équipe conformité.")
        else:
            with st.form("kyc"):
                st.file_uploader("Pièce d'identité", type=["pdf", "jpg", "png"])
                st.file_uploader("Justificatif de domicile (< 3 mois)", type=["pdf", "jpg", "png"])
                if st.form_submit_button("Envoyer pour vérification"):
                    db.set_kyc(u["id"], "en_cours")
                    st.rerun()

    if u["role"] == "porteur":
        mine = db.projects_df(include_hidden=True)
        mine = mine[mine["owner_id"] == u["id"]]
        c = st.columns(4)
        kpi(c[0], num(len(mine)), "Mes projets")
        kpi(c[1], eur(mine["raised"].sum()), "Total collecté")
        kpi(c[2], num(mine["backers"].sum()), "Contributeurs")
        kpi(c[3], num(db.unread_count(u["id"])), "Messages non lus")
        st.write("")
        if mine.empty:
            st.info("Vous n'avez pas encore de projet. Rendez-vous dans « Soumettre un projet ».")
        for _, p in mine.iterrows():
            with st.container(border=True):
                a, b = st.columns([3, 1])
                a.markdown(f"### {esc(p['title'])} {status_pill(p['status'])}", unsafe_allow_html=True)
                a.progress(min(p["pct"] / 100, 1.0), text=f"{eur(p['raised'])} / {eur(p['goal'])} · score critères {p['criteria_score']:.0f}/100")
                if p["admin_note"]:
                    a.caption(f"Note de l'équipe ÉLAN : {p['admin_note']}")
                if b.button("Voir la fiche", key=f"my_{p['id']}"):
                    go_to("Fiche projet", project_id=int(p["id"]))
                if p["status"] in ("en_cours", "finance"):
                    with st.expander("📰 Publier une actualité / un résultat d'impact"):
                        with st.form(f"upd_{p['id']}", clear_on_submit=True):
                            t = st.text_input("Titre")
                            body = st.text_area("Message aux contributeurs")
                            c1, c2, c3, c4 = st.columns(4)
                            j = c1.number_input("Emplois créés", 0, 1000, 0, key=f"j{p['id']}")
                            bn = c2.number_input("Bénéficiaires", 0, 10**6, 0, key=f"b{p['id']}")
                            co = c3.number_input("CO₂ évité (t)", 0.0, 10**5 * 1.0, 0.0, key=f"c{p['id']}")
                            rv = c4.number_input("Chiffre d'affaires (€)", 0.0, 10**8 * 1.0, 0.0, key=f"r{p['id']}")
                            if st.form_submit_button("Publier") and t:
                                db.add_update(int(p["id"]), t, body, j, bn, co, rv)
                                st.success("Actualité publiée.")
                                st.rerun()
                cl = contrib_df[contrib_df["project_id"] == p["id"]] if not contrib_df.empty else contrib_df
                if not cl.empty:
                    daily = cl[cl["status"] == "confirme"].set_index("created_at").resample("W")["amount"].sum().cumsum().reset_index()
                    st.plotly_chart(plot_style(px.area(daily, x="created_at", y="amount", title="Collecte cumulée (€)"), 240),
                                    width="stretch", key=f"chart_{p['id']}")

    elif u["role"] == "investisseur":
        mine = contrib_df[contrib_df["user_id"] == u["id"]] if not contrib_df.empty else contrib_df
        c = st.columns(4)
        kpi(c[0], eur(mine["amount"].sum() if not mine.empty else 0), "Total engagé")
        kpi(c[1], num(mine["project_id"].nunique() if not mine.empty else 0), "Projets soutenus")
        if not mine.empty:
            proj_ids = mine["project_id"].unique()
            sup = all_df[all_df["id"].isin(proj_ids)]
            kpi(c[2], num(sup["jobs_done"].sum()), "Emplois co-financés")
        else:
            kpi(c[2], "0", "Emplois co-financés")
        kpi(c[3], num(len(db.favorites(u["id"]))), "Favoris")
        st.write("")

        t1, t2, t3 = st.tabs(["📁 Mon portefeuille", "🎯 Mes préférences", "⭐ Favoris & recommandations"])
        with t1:
            if mine.empty:
                st.caption("Vous n'avez encore soutenu aucun projet.")
            else:
                a, b = st.columns(2)
                a.plotly_chart(plot_style(px.pie(mine, names="sector", values="amount", hole=.5, title="Par secteur")), width="stretch")
                b.plotly_chart(plot_style(px.pie(mine, names="kind", values="amount", hole=.5, title="Par mode")), width="stretch")
                t = mine[["created_at", "title", "kind", "amount", "status"]].sort_values("created_at", ascending=False)
                t.columns = ["Date", "Projet", "Type", "Montant €", "Statut"]
                st.dataframe(t, hide_index=True, width="stretch")
        with t2:
            prefs = db.get_prefs(u["id"])
            with st.form("prefs"):
                st.caption("Ces préférences servent à classer les projets par adéquation dans « Explorer ».")
                sectors = st.multiselect("Secteurs privilégiés", list(db.SECTORS), default=prefs.get("sectors", []))
                regions = st.multiselect("Territoires privilégiés", db.REGIONS, default=prefs.get("regions", []))
                modes = st.multiselect("Modes de financement", list(db.MODES), format_func=db.MODES.get, default=prefs.get("modes", []))
                odd = st.multiselect("ODD prioritaires", list(db.ODD), format_func=lambda k: f"ODD {k} · {db.ODD[k]}", default=prefs.get("odd", []))
                max_ticket = st.number_input("Ticket maximum par projet (€)", 0, 1_000_000, int(prefs.get("max_ticket", 0) or 0), 50)
                st.markdown("**Pondération du classement**")
                w = prefs.get("weights", {})
                cs = st.columns(6)
                weights = {k: cs[i].slider(lbl, 0, 50, int(w.get(k, d)), 5) for i, (k, lbl, d) in enumerate(
                    [("sector", "Secteur", 25), ("region", "Territoire", 15), ("mode", "Mode", 15),
                     ("odd", "ODD", 15), ("ticket", "Ticket", 10), ("criteria", "Critères", 20)])}
                if st.form_submit_button("Enregistrer mes préférences", type="primary"):
                    db.save_prefs(u["id"], {"sectors": sectors, "regions": regions, "modes": modes, "odd": odd,
                                            "max_ticket": max_ticket, "weights": weights})
                    st.success("Préférences enregistrées.")
        with t3:
            favs = db.favorites(u["id"])
            if favs:
                st.markdown("**Mes favoris**")
                card_grid(all_df[all_df["id"].isin(favs)], prefix="fav")
            prefs = db.get_prefs(u["id"])
            live = all_df[all_df["status"] == "en_cours"].copy()
            if not live.empty:
                live["match"] = live.apply(lambda p: db.match_score(p, prefs), axis=1)
                st.markdown("**Recommandés pour vous**")
                card_grid(live.nlargest(3, "match"), 3, lambda p: f"Adéquation <b>{p['match']:.0f}</b>/100", prefix="reco")
    else:
        st.info("Utilisez l'onglet « Administration » pour gérer la plateforme.")


def page_admin():
    if not u or u["role"] != "admin":
        st.error("Accès réservé aux administrateurs.")
        return
    st.title("🛡️ Administration & conformité")
    full = db.projects_df(include_hidden=True)
    pending = full[full["status"] == "en_revue"]
    alerts = contrib_df[contrib_df["status"] == "en_revue"] if not contrib_df.empty else contrib_df
    users = pd.DataFrame(db.list_users())
    kyc_q = users[users["kyc_status"] == "en_cours"]
    c = st.columns(4)
    kpi(c[0], num(len(pending)), "Projets à valider")
    kpi(c[1], num(len(kyc_q)), "KYC à traiter")
    kpi(c[2], num(len(alerts)), "Alertes LCB-FT")
    kpi(c[3], num(len(users)), "Utilisateurs")
    st.write("")
    t1, t2, t3, t4 = st.tabs(["📋 Modération des projets", "🪪 KYC", "🚨 Alertes transactions", "👥 Utilisateurs"])
    with t1:
        if pending.empty:
            st.success("Aucun projet en attente.")
        for _, p in pending.iterrows():
            with st.container(border=True):
                a, b = st.columns([2, 1])
                a.markdown(f"### {esc(p['title'])}")
                a.caption(f"{p['owner_name']} · {p['sector']} · {p['region']} · {db.MODES[p['mode']]} · objectif {eur(p['goal'])}")
                a.write(p["tagline"])
                for k, lbl, _ in db.CRITERIA:
                    a.markdown(f"{'✔' if p['criteria'][k] else '✘'} {lbl}")
                b.metric("Score de critères", f"{p['criteria_score']:.0f}/100")
                if p["owner_kyc"] != "verifie":
                    b.warning("KYC du porteur non vérifié")
                note = b.text_area("Note au porteur", key=f"note_{p['id']}")
                if b.button("✅ Publier", key=f"ok_{p['id']}", type="primary", width="stretch"):
                    db.update_project(int(p["id"]), status="en_cours", admin_note=note or None)
                    db.send_message(u["id"], int(p["owner_id"]), f"Votre projet « {p['title']} » est en ligne ! {note}", project_id=int(p["id"]))
                    st.rerun()
                if b.button("❌ Refuser", key=f"ko_{p['id']}", width="stretch"):
                    db.update_project(int(p["id"]), status="rejete", admin_note=note or "Dossier incomplet")
                    db.send_message(u["id"], int(p["owner_id"]), f"Votre projet « {p['title']} » n'a pas été retenu. Motif : {note or 'dossier incomplet'}", project_id=int(p["id"]))
                    st.rerun()
                if b.button("👁️ Aperçu", key=f"pv_{p['id']}", width="stretch"):
                    go_to("Fiche projet", project_id=int(p["id"]))
    with t2:
        if kyc_q.empty:
            st.success("Aucun dossier KYC en attente.")
        for _, r in kyc_q.iterrows():
            a, b, c2 = st.columns([3, 1, 1])
            a.markdown(f"**{esc(r['name'])}** · {r['email']} · {r['role']}")
            if b.button("Valider", key=f"kv_{r['id']}"):
                db.set_kyc(int(r["id"]), "verifie")
                st.rerun()
            if c2.button("Rejeter", key=f"kr_{r['id']}"):
                db.set_kyc(int(r["id"]), "non_verifie")
                st.rerun()
    with t3:
        st.caption(f"Règles actives : contribution unitaire ≥ {num(db.ALERT_SINGLE_AMOUNT)} € ; montant > 150 % du reste à financer ; "
                   f"KYC exigé au-delà de {num(db.KYC_THRESHOLD)} € cumulés et pour tout prêt/investissement.")
        if alerts.empty:
            st.success("Aucune transaction en revue.")
        for _, r in alerts.iterrows():
            with st.container(border=True):
                a, b, c2 = st.columns([3, 1, 1])
                a.markdown(f"**{eur(r['amount'])}** · {r['kind']} · {esc(r['contributor'])} (KYC : {r['kyc_status']}) → {esc(r['title'])}")
                a.caption(f"⚠️ {r['alert']} · {str(r['created_at'])[:16]}")
                if b.button("Valider", key=f"cv_{r['id']}"):
                    db.set_contribution_status(int(r["id"]), "confirme")
                    st.rerun()
                if c2.button("Bloquer", key=f"cb_{r['id']}"):
                    db.set_contribution_status(int(r["id"]), "refuse")
                    st.rerun()
        if not contrib_df.empty:
            top = contrib_df.groupby("contributor")["amount"].sum().nlargest(10).reset_index()
            st.plotly_chart(plot_style(px.bar(top, x="amount", y="contributor", orientation="h", title="Top 10 contributeurs (montants cumulés)")), width="stretch")
    with t4:
        st.dataframe(users, hide_index=True, width="stretch")


ROUTES = {"Accueil": page_home, "Explorer les projets": page_explore, "Projets financés": page_funded,
          "Statistiques": page_stats, "Messagerie": page_messages, "Soumettre un projet": page_submit,
          "Mon espace": page_me, "Administration": page_admin, "Fiche projet": page_project}
ROUTES.get(page, page_home)()

st.markdown(
    "<div class='disclaimer'>ÉLAN — prototype de démonstration : les paiements sont simulés. Une mise en production "
    "en France nécessite l'agrément de prestataire de services de financement participatif (PSFP, règlement UE 2020/1503) "
    "délivré par l'AMF, un partenariat avec un établissement de paiement agréé et un dispositif LCB-FT complet. "
    "Investir dans de jeunes entreprises comporte un risque de perte totale ou partielle du capital.</div>",
    unsafe_allow_html=True,
)
