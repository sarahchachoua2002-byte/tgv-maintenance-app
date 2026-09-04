"""
Chatbot Maintenance TGV — propulsé par Grok (xAI).
"""
import pandas as pd
from openai import OpenAI

import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

_context_cache = {}

def _get_model():
    """Retourne le premier modèle de chat disponible sur ce compte Groq."""
    try:
        models = client.models.list()
        for m in models.data:
            mid = m.id
            if any(k in mid for k in ['llama', 'gemma', 'mixtral', 'qwen', 'deepseek']):
                print(f"[GROQ] Modèle sélectionné : {mid}", flush=True)
                return mid
    except Exception as e:
        print(f"[GROQ] Impossible de lister les modèles : {e}", flush=True)
    return "llama-3.3-70b-versatile"

_MODEL = _get_model()


def _build_context():
    """Construit un résumé des données réelles à envoyer à Grok."""
    if 'ctx' in _context_cache:
        return _context_cache['ctx']

    from data_loader import load_data, _cache
    load_data()
    df_merge = _cache['df_merge']
    df_prog_un = _cache.get('df_prog_unmatched', pd.DataFrame())

    # Infos générales
    nb_real   = len(df_merge)
    nb_nonreal = len(df_prog_un)
    nb_rames  = df_merge['n__rame'].nunique()
    sites     = sorted(df_merge['site'].dropna().unique().tolist()) if 'site' in df_merge.columns else []
    cats      = sorted(df_merge['categorie'].dropna().unique().tolist())

    # Taux de réalisation par catégorie
    taux_cat = {}
    for cat in cats:
        nr = len(df_merge[df_merge['categorie'] == cat])
        nn = len(df_prog_un[df_prog_un['categorie'] == cat]) if not df_prog_un.empty else 0
        total = nr + nn
        taux_cat[cat] = f"{round(100*nr/total)}%" if total > 0 else "N/A"

    # Rames par site
    rames_par_site = {}
    if 'site' in df_merge.columns:
        for site in sites:
            rames = df_merge[df_merge['site'] == site]['n__rame'].unique().tolist()
            rames_par_site[site] = sorted([str(r) for r in rames])

    # Écart moyen par catégorie
    ecarts = {}
    for cat in cats:
        sub = df_merge[df_merge['categorie'] == cat]['ecart_debut_h']
        if len(sub) > 0:
            ecarts[cat] = f"{round(sub.mean(), 1)}h"

    # Taux de réalisation par site
    # Logique : pour chaque site, on regarde les rames qui y ont opéré
    # et on calcule leur taux global de réalisation (réalisées / planifiées toutes ops confondues)
    taux_site = {}
    if 'site' in df_merge.columns:
        for site in sites:
            rames_site = df_merge[df_merge['site'] == site]['n__rame'].unique()
            nr = len(df_merge[df_merge['site'] == site])
            # ops non réalisées pour ces mêmes rames
            nn = len(df_prog_un[df_prog_un['n__rame'].isin(rames_site)]) if not df_prog_un.empty else 0
            total = nr + nn
            taux_site[site] = f"{round(100*nr/total)}% ({nr} réalisées / {total} planifiées)" if total > 0 else f"{nr} opérations réalisées"

    # Top 10 rames avec le plus grand écart moyen
    ecarts_rame = df_merge.groupby('n__rame')['ecart_debut_h'].mean().sort_values(ascending=False)
    top_retards = ecarts_rame.head(10).round(1).to_dict()
    top_avances = ecarts_rame.tail(5).round(1).to_dict()

    # Top 5 opérations les plus fréquentes
    top_ops = df_merge['code_op'].value_counts().head(10).to_dict()

    # Semaines disponibles
    col_sem = 'semaine_iso' if 'semaine_iso' in df_merge.columns else 'semaine_annee'
    sems = sorted(df_merge[col_sem].dropna().astype(int).unique().tolist())

    # Stats par semaine
    stats_sem = {}
    for s in sems:
        sub = df_merge[df_merge[col_sem] == s]
        col_sem_un = 'semaine_iso' if not df_prog_un.empty and 'semaine_iso' in df_prog_un.columns else 'semaine_annee'
        un  = df_prog_un[df_prog_un[col_sem_un] == s] if not df_prog_un.empty and col_sem_un in df_prog_un.columns else pd.DataFrame()
        stats_sem[s] = {'real': len(sub), 'non_real': len(un), 'rames': sub['n__rame'].nunique()}

    ctx = f"""Tu es l'assistant IA de l'application de maintenance TGV SNCF Voyageurs.
Tu réponds en français, de façon concise et professionnelle.
Tu as accès aux données RÉELLES de maintenance S1 à S12 2026.
IMPORTANT : utilise UNIQUEMENT les données ci-dessous pour répondre. Ne dis jamais que tu n'as pas accès aux données.

=== DONNÉES DISPONIBLES ===

Période : Semaines S1 à S12 2026
Opérations réalisées : {nb_real}
Opérations non réalisées : {nb_nonreal}
Rames suivies : {nb_rames}
Semaines : {sems}

Sites de maintenance : {', '.join(sites)}

Catégories d'opérations : {', '.join(cats)}

Taux de réalisation par catégorie :
{chr(10).join(f"  - {cat} : {taux}" for cat, taux in taux_cat.items())}

Écart moyen de début (planifié vs réel) par catégorie — RÈGLE : valeur POSITIVE = retard (réalisé après le planifié), valeur NÉGATIVE = avance (réalisé avant le planifié). La catégorie avec le plus de RETARD est celle avec l'écart le plus POSITIF. Ne pas confondre valeur négative élevée avec un retard :
{chr(10).join(f"  - {cat} : {ec}" for cat, ec in ecarts.items())}

Rames par site de maintenance :
{chr(10).join(f"  - {site} : {', '.join(rames[:20])}{'...' if len(rames)>20 else ''}" for site, rames in rames_par_site.items())}

Top 10 rames avec le plus grand retard moyen (écart début planifié vs réel en heures) :
{chr(10).join(f"  - Rame {r} : +{v}h de retard moyen" for r, v in top_retards.items())}

Top 5 rames les plus en avance :
{chr(10).join(f"  - Rame {r} : {v}h" for r, v in top_avances.items())}

Taux de réalisation par site :
{chr(10).join(f"  - {site} : {taux}" for site, taux in taux_site.items())}

Codes opérations les plus fréquents :
{chr(10).join(f"  - {code} : {n} fois" for code, n in top_ops.items())}

Opérations réalisées par semaine :
{chr(10).join(f"  - S{s} : {v['real']} réalisées, {v['non_real']} non réalisées, {v['rames']} rames" for s, v in stats_sem.items())}

=== CORRESPONDANCES SITES ===
Les codes sites correspondent aux villes françaises. BXG = Bordeaux, MPL = Montpellier, NST = Nantes ou Nancy, FOR = Forbach, LL = Le Landy (Paris), PSE = Paris Sud-Est, MSC = Strasbourg, NSA = Nancy, CIH = Chambéry, CIB = site CIB.

=== RÈGLES STRICTES ===
- Réponds TOUJOURS en français
- Utilise UNIQUEMENT les données fournies ci-dessus
- Ne dis JAMAIS que tu n'as pas accès aux données — tu les as toutes
- Si on demande "rames à Bordeaux" → cherche le site BXG dans les données
- Si on demande "planning S5" → utilise les stats de la semaine S5 ci-dessus
- Sois concis (3-5 lignes max)
- Si vraiment une info n'est pas dans les données, dis-le clairement
"""

    _context_cache['ctx'] = ctx
    return ctx


def answer(message, history=None):
    """Envoie la question à Grok avec le contexte des données."""
    try:
        context = _build_context()

        messages = [{"role": "system", "content": context}]

        # Historique de conversation (mémoire des échanges précédents)
        if history:
            for h in history[-6:]:  # garder les 6 derniers échanges
                messages.append({"role": "user",      "content": h["user"]})
                messages.append({"role": "assistant",  "content": h["bot"]})

        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            max_tokens=400,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"[GROQ ERROR] {type(e).__name__}: {e}", flush=True)
        return _fallback(message)


def _fallback(message):
    """Réponses basées sur les règles si l'API Grok n'est pas disponible."""
    import re
    from data_loader import _cache, load_data
    load_data()
    df_merge   = _cache['df_merge']
    df_prog_un = _cache.get('df_prog_unmatched', pd.DataFrame())

    t = message.strip().lower()

    # aide
    if any(k in t for k in ['aide', 'help', 'bonjour', 'salut']):
        return ("👋 Je suis l'assistant maintenance TGV.\n"
                "Pose-moi des questions sur les rames, sites, plannings ou opérations.\n"
                "Ex: *Planning rame 4702*, *Rames à BXG*, *Taux réalisation MODULE*")

    # numéro de rame
    m = re.search(r'\b(\d{4,})\b', t)
    if m:
        rame = m.group(1)
        sub  = df_merge[df_merge['n__rame'].astype(str) == rame]
        if sub.empty:
            return f"Aucune donnée pour la rame {rame}."
        lines = [f"🚄 **Rame {rame}** — {len(sub)} opération(s) réalisée(s) :"]
        for _, r in sub.sort_values('debut_planifie').head(8).iterrows():
            sem_val = r.get('semaine_annee', r.get('semaine_iso'))
            sem  = int(sem_val) if pd.notna(sem_val) else '?'
            lines.append(f"  • S{sem} — {r.get('categorie','?')} / {r.get('code_op','?')} @ {r.get('site','?')}")
        return '\n'.join(lines)

    # site
    if 'site' in t and any(k in t for k in ['liste', 'quels', 'disponible']):
        sites = sorted(df_merge['site'].dropna().unique())
        return f"📍 Sites : {', '.join(sites)}"

    # taux
    if any(k in t for k in ['taux', 'réalisation', 'realisation']):
        cats = df_merge['categorie'].dropna().unique()
        lines = ["📊 **Taux de réalisation par catégorie** :"]
        for cat in sorted(cats):
            nr = len(df_merge[df_merge['categorie'] == cat])
            nn = len(df_prog_un[df_prog_un['categorie'] == cat]) if not df_prog_un.empty else 0
            total = nr + nn
            taux = round(100*nr/total) if total > 0 else 0
            lines.append(f"  • {cat} : {taux}%")
        return '\n'.join(lines)

    return "⚠️ Assistant temporairement indisponible. Veuillez réessayer dans quelques instants."


def list_models():
    """Retourne les modèles disponibles sur ce compte xAI."""
    try:
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception as e:
        return [f"Erreur : {e}"]
