import json
import sys
import os
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import data_loader as dl
import chatbot

app = Flask(__name__)
app.secret_key = 'tgv_maintenance_2026'

USERS = {
    'user': {'password': 'user', 'role': 'Programmeur', 'nom': 'Utilisateur'},
}


def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# ── AUTH ────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username in USERS and USERS[username]['password'] == password:
            session['user'] = {
                'username': username,
                'role':     USERS[username]['role'],
                'nom':      USERS[username]['nom'],
            }
            return redirect(url_for('dashboard'))
        error = 'Identifiants incorrects. Veuillez réessayer.'
    return render_template('login_v2.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    import math

    _, _, df_all = dl.load_data()

    # Séparer fiable / non-fiable dès le départ
    df_fiable    = df_all[df_all['match_fiable'] == True].copy()
    df_nonfiable = df_all[df_all['match_fiable'] == False].copy()

    # Stats non-fiables pour la carte alerte (toujours sur l'ensemble, sans filtre)
    nb_nonfiable      = len(df_nonfiable)
    nb_rames_nf       = df_nonfiable['n__rame'].nunique()
    cats_nf           = sorted(df_nonfiable['categorie'].dropna().unique().tolist())

    # Listes pour les filtres (sur données fiables uniquement)
    all_semaines   = sorted(df_fiable['semaine_iso'].dropna().unique().astype(int).tolist())
    all_categories = sorted(df_fiable['categorie'].dropna().unique().tolist())

    # Filtres actifs (GET params)
    f_semaine  = request.args.get('semaine', '')
    f_categorie = request.args.get('categorie', '')

    # Appliquer les filtres sur données fiables uniquement
    df = df_fiable.copy()
    if f_semaine:
        df = df[df['semaine_iso'] == int(f_semaine)]
    if f_categorie:
        df = df[df['categorie'] == f_categorie]

    # ── KPIs calculés sur df filtré ──────────────────────────────────────────
    nb_ops    = len(df)
    nb_rames  = df['n__rame'].nunique()
    ecart_moy = round(float(df['ecart_debut_h'].mean()), 1) if nb_ops > 0 else 0.0
    taux_nc   = round(float((df['ecart_butee_h'] > 0).mean() * 100), 1) \
                if nb_ops > 0 and df['ecart_butee_h'].notna().any() else 0.0

    kpis = {
        'nb_operations': nb_ops,
        'nb_rames':      nb_rames,
        'ecart_moyen':   ecart_moy,
        'taux_nc':       taux_nc,
    }

    # ── Alertes (toujours sur données complètes) ─────────────────────────────
    raw_alertes = dl.get_alertes()
    alertes = []
    for a in raw_alertes:
        niveau = 'critique' if a['type'] == 'danger' else ('warning' if a['type'] == 'warning' else 'info')
        titre  = a['titre']
        alertes.append({
            'niveau':  niveau,
            'rame':    titre.split('—')[-1].strip() if '—' in titre else titre,
            'message': titre.split('—')[0].strip()  if '—' in titre else titre,
            'detail':  a['detail'],
        })

    # ── Dernières opérations sur df filtré ───────────────────────────────────
    df_recent = (df.dropna(subset=['debut_reel'])
                   .sort_values('debut_reel', ascending=False)
                   .head(20))
    dernieres_ops = []
    for _, row in df_recent.iterrows():
        sem = row.get('semaine_iso', None)
        dernieres_ops.append({
            'n_rame':      row['n__rame'],
            'code_op':     row['code_op'],
            'categorie':   row.get('categorie', '—'),
            'semaine':     int(sem) if sem is not None and not (isinstance(sem, float) and math.isnan(sem)) else '—',
            'ecart_debut': round(float(row['ecart_debut_h']), 1) if not (isinstance(row['ecart_debut_h'], float) and math.isnan(row['ecart_debut_h'])) else 0,
        })

    # ── Graphique historique (par semaine si pas de filtre semaine) ───────────
    if f_semaine:
        # Regrouper par catégorie si filtre semaine actif
        grp = df.groupby('categorie').agg(
            ecart_moyen_h=('ecart_debut_h', 'mean'),
            taux_retard_pct=('ecart_debut_h', lambda x: (x > 0).mean() * 100),
        ).reset_index()
        histo_json = json.dumps({
            'labels':      grp['categorie'].tolist(),
            'ecart_debut': [round(float(v), 1) for v in grp['ecart_moyen_h'].tolist()],
            'ecart_duree': [round(float(v), 1) for v in grp['taux_retard_pct'].tolist()],
            'axe_x':       'Catégorie',
        })
    else:
        grp = df.groupby('semaine_iso').agg(
            ecart_moyen_h=('ecart_debut_h', 'mean'),
            taux_retard_pct=('ecart_debut_h', lambda x: (x > 0).mean() * 100),
        ).reset_index().sort_values('semaine_iso')
        histo_json = json.dumps({
            'labels':      [f'S{int(s)}' for s in grp['semaine_iso'].tolist()],
            'ecart_debut': [round(float(v), 1) for v in grp['ecart_moyen_h'].tolist()],
            'ecart_duree': [round(float(v), 1) for v in grp['taux_retard_pct'].tolist()],
            'axe_x':       'Semaine',
        })

    # ── Donut flottes sur df filtré ───────────────────────────────────────────
    fl = df.groupby('flotte')['ecart_debut_h'].count().reset_index()
    fl.columns = ['flotte', 'nb']
    flottes_json = json.dumps({
        'labels': [f'Flotte {v}' for v in fl['flotte'].tolist()],
        'values': [int(v) for v in fl['nb'].tolist()],
    })

    raw_kpis = dl.get_kpis()

    return render_template('dashboard_v2.html',
        kpis=kpis,
        alertes=alertes,
        dernieres_ops=dernieres_ops,
        histo_json=histo_json,
        flottes_json=flottes_json,
        sim_date=raw_kpis['sim_semaine'],
        all_semaines=all_semaines,
        all_categories=all_categories,
        f_semaine=f_semaine,
        f_categorie=f_categorie,
        nb_nonfiable=nb_nonfiable,
        nb_rames_nf=nb_rames_nf,
        cats_nf=cats_nf,
    )


def _isnan(v):
    try:
        import math
        return math.isnan(float(v))
    except Exception:
        return False


# ── PAGES STUB ───────────────────────────────────────────────────────────────

def _stub(titre, icone):
    return f"""
    <!DOCTYPE html><html lang="fr">
    <head><meta charset="UTF-8"><title>{titre}</title>
    <style>
      body{{font-family:'Segoe UI',sans-serif;display:flex;align-items:center;justify-content:center;
            height:100vh;margin:0;background:#F4F6FA;}}
      .box{{text-align:center;background:#fff;padding:48px 64px;border-radius:16px;
             border:1px solid #E2E8F0;}}
      .ico{{font-size:52px;margin-bottom:16px}}
      h2{{color:#1A202C;margin:0 0 8px}}
      p{{color:#718096;margin:0 0 24px;font-size:14px}}
      a{{display:inline-block;padding:10px 24px;background:#E30613;color:#fff;
         border-radius:8px;text-decoration:none;font-weight:600;font-size:14px}}
    </style></head>
    <body><div class="box">
      <div class="ico">{icone}</div>
      <h2>{titre}</h2>
      <p>Page en cours de construction — revenez bientôt !</p>
      <a href="/dashboard">← Tableau de bord</a>
    </div></body></html>"""


@app.route('/parc')
@login_required
def parc():
    import math
    _, _, df_all = dl.load_data()
    df = df_all[df_all['match_fiable'] == True].copy()

    grp = df.groupby('n__rame').agg(
        flotte=('flotte', 'first'),
        nb_ops=('ecart_debut_h', 'count'),
        ecart_moy=('ecart_debut_h', 'mean'),
        taux_retard=('ecart_debut_h', lambda x: round(float((x > 0).mean() * 100), 1)),
        derniere_op=('debut_reel', 'max'),
    ).reset_index().sort_values('nb_ops', ascending=False)

    rames = []
    for _, row in grp.iterrows():
        em = row['ecart_moy']
        rames.append({
            'n_rame':       row['n__rame'],
            'flotte':       str(int(row['flotte'])) if pd.notna(row['flotte']) else '—',
            'nb_ops':       int(row['nb_ops']),
            'ecart_moy':    round(float(em), 1) if not (isinstance(em, float) and math.isnan(em)) else 0.0,
            'taux_retard':  row['taux_retard'],
            'derniere_op':  row['derniere_op'].strftime('%d/%m/%Y') if pd.notna(row['derniere_op']) else '—',
        })

    nb_rames   = len(rames)
    nb_flottes = grp['flotte'].nunique()

    return render_template('parc_v2.html',
        rames=rames,
        nb_rames=nb_rames,
        nb_flottes=int(nb_flottes),
    )


@app.route('/rame/<n_rame>')
@login_required
def rame_detail(n_rame):
    import math
    _, _, df_all = dl.load_data()
    df = df_all[(df_all['match_fiable'] == True) & (df_all['n__rame'] == n_rame)].copy()

    if df.empty:
        return redirect(url_for('parc'))

    flotte    = str(int(df['flotte'].iloc[0])) if pd.notna(df['flotte'].iloc[0]) else '—'
    nb_ops    = len(df)
    ecart_moy = round(float(df['ecart_debut_h'].mean()), 1)
    taux_ret  = round(float((df['ecart_debut_h'] > 0).mean() * 100), 1)

    # Répartition par catégorie
    cats = df.groupby('categorie').agg(
        nb=('ecart_debut_h', 'count'),
        ecart_moy=('ecart_debut_h', 'mean'),
    ).reset_index()
    cats_json = json.dumps({
        'labels': cats['categorie'].tolist(),
        'nb':     [int(v) for v in cats['nb'].tolist()],
        'ecart':  [round(float(v), 1) for v in cats['ecart_moy'].tolist()],
    })

    # Évolution par semaine
    sem = df.groupby('semaine_iso').agg(
        ecart_moy=('ecart_debut_h', 'mean'),
    ).reset_index().sort_values('semaine_iso')
    sem_json = json.dumps({
        'labels': [f'S{int(s)}' for s in sem['semaine_iso'].tolist()],
        'ecart':  [round(float(v), 1) for v in sem['ecart_moy'].tolist()],
    })

    # Toutes les opérations de la rame
    ops = []
    for _, row in df.sort_values('debut_reel', ascending=False).iterrows():
        s = row.get('semaine_iso')
        ops.append({
            'code_op':     row['code_op'],
            'categorie':   row.get('categorie', '—'),
            'semaine':     int(s) if s and not (isinstance(s, float) and math.isnan(s)) else '—',
            'debut_reel':  row['debut_reel'].strftime('%d/%m/%Y %H:%M') if pd.notna(row['debut_reel']) else '—',
            'ecart_debut': round(float(row['ecart_debut_h']), 1),
        })

    return render_template('rame_detail_v2.html',
        n_rame=n_rame,
        flotte=flotte,
        nb_ops=nb_ops,
        ecart_moy=ecart_moy,
        taux_retard=taux_ret,
        cats_json=cats_json,
        sem_json=sem_json,
        ops=ops,
    )


@app.route('/planning')
@login_required
def planning():
    data = dl.get_planning_data()

    sem_json = json.dumps({
        'labels':      [d['sem'] for d in data['sem_data']],
        'planifie':    [d['planifie'] for d in data['sem_data']],
        'realise':     [d['realise'] for d in data['sem_data']],
        'non_realise': [d['non_realise'] for d in data['sem_data']],
        'taux':        [d['taux'] for d in data['sem_data']],
    })

    cat_json = json.dumps({
        'labels':      [d['categorie'] for d in data['cat_data']],
        'taux':        [d['taux'] for d in data['cat_data']],
        'realise':     [d['realise'] for d in data['cat_data']],
        'non_realise': [d['non_realise'] for d in data['cat_data']],
    })

    return render_template('planning_v2.html',
        nb_planifie=data['nb_planifie'],
        nb_realise=data['nb_realise'],
        nb_non_realise=data['nb_non_realise'],
        taux_realisation=data['taux_realisation'],
        sem_json=sem_json,
        cat_json=cat_json,
        ops_nr=data['ops_nr'],
    )


@app.route('/historique')
@login_required
def historique():
    import math
    _, _, df_all = dl.load_data()
    df_f  = df_all[df_all['match_fiable'] == True].copy()
    df_nf = df_all[df_all['match_fiable'] == False].copy()

    # Historique fiable par semaine
    grp = df_f.groupby('semaine_iso').agg(
        nb=('ecart_debut_h','count'),
        ecart_moy=('ecart_debut_h','mean'),
        taux_retard=('ecart_debut_h', lambda x: (x>0).mean()*100),
        taux_nc=('ecart_butee_h', lambda x: (x>0).mean()*100 if x.notna().any() else 0),
    ).reset_index().sort_values('semaine_iso')

    histo_json = json.dumps({
        'labels':       [f'S{int(s)}' for s in grp['semaine_iso'].tolist()],
        'nb':           [int(v) for v in grp['nb'].tolist()],
        'ecart_moy':    [round(float(v),1) for v in grp['ecart_moy'].tolist()],
        'taux_retard':  [round(float(v),1) for v in grp['taux_retard'].tolist()],
        'taux_nc':      [round(float(v),1) for v in grp['taux_nc'].tolist()],
    })

    # Table fiable (50 dernières)
    ops_fiables = []
    for _, row in df_f.sort_values('debut_reel', ascending=False).head(50).iterrows():
        sem = row.get('semaine_iso')
        ops_fiables.append({
            'n_rame':      row['n__rame'],
            'code_op':     row['code_op'],
            'categorie':   row.get('categorie','—'),
            'semaine':     int(sem) if sem and not (isinstance(sem,float) and math.isnan(sem)) else '—',
            'debut_reel':  row['debut_reel'].strftime('%d/%m/%Y') if pd.notna(row['debut_reel']) else '—',
            'ecart_debut': round(float(row['ecart_debut_h']),1),
            'statut':      row.get('statut_conformite','—'),
        })

    # Table non-fiable (toutes)
    ops_nf = []
    for _, row in df_nf.sort_values('debut_reel', ascending=False).iterrows():
        ops_nf.append({
            'n_rame':         row['n__rame'],
            'code_op':        row['code_op'],
            'categorie':      row.get('categorie','—'),
            'debut_reel':     row['debut_reel'].strftime('%d/%m/%Y') if pd.notna(row['debut_reel']) else '—',
            'fin_reelle':     row['fin_reelle'].strftime('%d/%m/%Y') if pd.notna(row.get('fin_reelle')) else '—',
            'debut_planifie': row['debut_planifie'].strftime('%d/%m/%Y') if pd.notna(row['debut_planifie']) else '—',
            'ecart_debut':    round(float(row['ecart_debut_h']),1),
            'flotte':         str(int(row['flotte'])) if pd.notna(row.get('flotte')) else '—',
        })

    return render_template('historique_v2.html',
        histo_json=histo_json,
        ops_fiables=ops_fiables,
        ops_nf=ops_nf,
        nb_fiable=len(df_f),
        nb_nf=len(df_nf),
    )


@app.route('/prediction', methods=['GET', 'POST'])
@login_required
def prediction():
    import math

    dl.train_classification_model()

    _, _, df_all = dl.load_data()
    df_fiable = df_all[df_all['match_fiable'] == True]

    all_categories = sorted(df_fiable['categorie'].dropna().unique().tolist())
    all_rames      = sorted(df_fiable['n__rame'].unique().tolist())
    all_sites      = dl.get_liste_sites()
    from datetime import date
    semaine_prochaine = date.today().isocalendar()[1] + 1

    clf_metrics = {'accuracy': dl._cache.get('clf_accuracy', '—')}

    clf_imp_raw  = dl._cache.get('clf_importances', [])
    clf_labels   = {
        'categorie_enc':  'Catégorie',
        'flotte_enc':     'Flotte',
        'code_enc':       'Code op.',
        'jour_semaine':   'Jour semaine',
        'jour_ferie':     'Jour férié',
        'taux_hist_cat':  'Taux hist. catégorie',
        'taux_hist_code': 'Taux hist. code op.',
        'site_enc':       'Site',
        'charge_semaine': 'Charge semaine',
        'cat_flotte_enc': 'Catégorie × Flotte',
    }
    clf_imp      = sorted(clf_imp_raw, key=lambda x: x[1], reverse=True)
    clf_imp_json = json.dumps({
        'labels': [clf_labels.get(f, f) for f, _ in clf_imp],
        'values': [round(float(v) * 100, 1) for _, v in clf_imp],
    })

    # Résultat prédiction si formulaire soumis
    result = None
    f_rame      = request.form.get('rame', '')
    f_categorie = request.form.get('categorie', '')
    f_code_op   = request.form.get('code_op', '')
    f_site      = request.form.get('site', '')
    f_semaine   = str(semaine_prochaine)

    if request.method == 'POST' and f_rame and f_categorie:
        # Probabilité de réalisation — modèle de classification calibré
        clf        = dl._cache['model_clf']
        le_cat2    = dl._cache['le_cat2']
        le_flotte2 = dl._cache['le_flotte2']
        le_code2   = dl._cache['le_code2']
        le_site2   = dl._cache.get('le_site2')

        rame_data = df_fiable[df_fiable['n__rame'] == f_rame]
        flotte = str(int(rame_data['flotte'].iloc[0])) if len(rame_data) > 0 and pd.notna(rame_data['flotte'].iloc[0]) else '0'

        try:
            cat_enc    = le_cat2.transform([f_categorie])[0]
        except Exception:
            cat_enc = 0
        try:
            flotte_enc = le_flotte2.transform([flotte])[0]
        except Exception:
            flotte_enc = 0
        try:
            site_enc = le_site2.transform([f_site if f_site else 'Inconnu'])[0] if le_site2 else 0
        except Exception:
            site_enc = 0
        try:
            code_enc = le_code2.transform([f_code_op.upper()])[0] if f_code_op else 0
        except Exception:
            code_enc = 0

        # Features supplémentaires alignées sur l'entraînement
        df_merge_c = dl._cache['df_merge']
        df_unmatched = dl._cache.get('df_prog_unmatched', pd.DataFrame())

        import holidays as _holidays
        from datetime import date as _date
        _today = _date.today()
        jour_semaine = _today.weekday()
        jour_ferie   = 1 if _today in _holidays.France(years=[_today.year]) else 0

        # Taux historiques — depuis les tables sauvegardées à l'entraînement
        taux_cat_dict   = dl._cache.get('taux_cat_dict', {})
        taux_code_dict  = dl._cache.get('taux_code_dict', {})
        charge_sem_dict = dl._cache.get('charge_sem_dict', {})

        taux_hist_cat  = taux_cat_dict.get(f_categorie, 0.5)
        code_up = f_code_op.upper() if f_code_op else ''
        taux_hist_code = taux_code_dict.get(code_up, taux_hist_cat)
        # Fallback sur le max des semaines S1-S12 (données d'entraînement)
        # La moyenne globale inclut des semaines futures avec très peu d'ops → biais bas
        charge_ref = max(charge_sem_dict.values()) if charge_sem_dict else 640
        charge_semaine = charge_sem_dict.get(semaine_prochaine, charge_ref)

        # Interaction catégorie × flotte
        le_catflotte = dl._cache.get('le_catflotte')
        cat_flotte_str = f"{f_categorie}_{flotte}"
        try:
            cat_flotte_enc = int(le_catflotte.transform([cat_flotte_str])[0]) if le_catflotte else 0
        except Exception:
            cat_flotte_enc = 0

        X_clf = [[cat_enc, flotte_enc, code_enc, site_enc,
                  jour_semaine, jour_ferie, taux_hist_cat, taux_hist_code,
                  charge_semaine, cat_flotte_enc]]
        proba_realise = round(float(clf.predict_proba(X_clf)[0][1]) * 100, 1)

        # Taux historique en contexte (fallback si pas de prédiction ML)
        taux_hist, nb_obs, niveau_proba = dl.get_taux_realisation_historique(
            site=f_site or None, categorie=f_categorie, code_op=f_code_op or None
        )

        # Libellé de l'opération sélectionnée (ou la catégorie si pas de code_op)
        libelle = dl.get_libelle_pour_operation(f_rame, f_categorie, f_code_op or None)

        # Écart moyen historique pour contexte
        ecart_hist, nb_ecart, _ = dl.get_ecart_historique(
            categorie=f_categorie, code_op=f_code_op or None, n_rame=f_rame
        )

        if proba_realise >= 60:
            reco = f"Réalisation probable ({proba_realise}%). Opération bien ancrée dans l'historique."
        elif proba_realise >= 40:
            reco = f"Probabilité modérée ({proba_realise}%). Maintenir un suivi régulier de cette opération."
        elif proba_realise >= 20:
            reco = f"Risque modéré ({proba_realise}%). Anticiper un éventuel report ou renforcer les ressources."
        else:
            reco = f"Risque élevé de non-réalisation ({proba_realise}%). Intervention recommandée en amont."

        result = {
            'rame':            f_rame,
            'categorie':       f_categorie,
            'code_op':         f_code_op or '—',
            'site':            f_site or '—',
            'libelle':         libelle or '—',
            'semaine':         f_semaine,
            'proba_realise':   proba_realise,
            'taux_hist':       taux_hist,
            'nb_obs':          nb_obs,
            'niveau_proba':    niveau_proba,
            'ecart_hist':      ecart_hist,
            'nb_ecart':        nb_ecart,
            'recommandation':  reco,
        }

    return render_template('prediction_v2.html',
        all_rames=all_rames,
        all_categories=all_categories,
        all_sites=all_sites,
        semaine_prochaine=semaine_prochaine,
        clf_metrics=clf_metrics,
        clf_imp_json=clf_imp_json,
        result=result,
        f_rame=f_rame,
        f_categorie=f_categorie,
        f_code_op=f_code_op,
        f_site=f_site,
    )


# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/operations/<n_rame>')
@login_required
def api_operations(n_rame):
    ops = dl.get_liste_operations(n_rame)
    return jsonify(ops)


@app.route('/api/sites_rame')
@login_required
def api_sites_rame():
    rame = request.args.get('rame', '')
    dl.load_data()
    df_m = dl._cache.get('df_merge', pd.DataFrame())
    df_u = dl._cache.get('df_prog_unmatched', pd.DataFrame())
    sites = set()
    for df in [df_m, df_u]:
        if 'site' in df.columns and not df.empty:
            mask = df['n__rame'].astype(str) == str(rame)
            sites.update(df[mask]['site'].dropna().unique().tolist())
    return jsonify(sorted(sites))


@app.route('/api/categories_rame_site')
@login_required
def api_categories_rame_site():
    rame = request.args.get('rame', '')
    site = request.args.get('site', '')
    dl.load_data()
    df_m = dl._cache.get('df_merge', pd.DataFrame())
    df_u = dl._cache.get('df_prog_unmatched', pd.DataFrame())
    cats = set()
    for df in [df_m, df_u]:
        if 'categorie' not in df.columns:
            continue
        mask = df['n__rame'].astype(str) == str(rame)
        if site and 'site' in df.columns:
            mask &= df['site'].astype(str) == site
        cats.update(df[mask]['categorie'].dropna().unique().tolist())
    return jsonify(sorted(cats))


@app.route('/api/categories_site')
@login_required
def api_categories_site():
    site = request.args.get('site', '')
    dl.load_data()
    df = dl._cache.get('df_merge')
    if df is None or 'site' not in df.columns:
        return jsonify([])
    sub = df[df['site'].astype(str) == site] if site else df
    cats = sorted(sub['categorie'].dropna().unique().tolist())
    return jsonify(cats)


@app.route('/api/operations_cat')
@login_required
def api_operations_cat():
    categorie = request.args.get('categorie', '')
    site      = request.args.get('site', '')
    dl.load_data()
    df = dl._cache.get('df_merge')
    if df is None:
        return jsonify([])
    mask = df['categorie'] == categorie
    if site and 'site' in df.columns:
        mask &= df['site'].astype(str) == site
    sub = df[mask]
    ops = sorted(sub['code_op'].dropna().unique().tolist())
    if 'libelle_operation' in sub.columns:
        lib_map = sub.groupby('code_op')['libelle_operation'].first().to_dict()
        result  = [{'code': c, 'libelle': lib_map.get(c) or c} for c in ops]
    else:
        result = [{'code': c, 'libelle': c} for c in ops]
    return jsonify(result)


@app.route('/api/chat/models')
def api_chat_models():
    return jsonify(chatbot.list_models())


@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user' not in session:
        return jsonify({'reply': 'Session expirée, reconnecte-toi.'})
    data    = request.get_json(force=True)
    msg     = data.get('message', '').strip()
    history = data.get('history', [])
    if not msg:
        return jsonify({'reply': "Écris ta question ici 👋"})
    reply = chatbot.answer(msg, history=history)
    return jsonify({'reply': reply})


# ── MAIN ──────────────────────────────────────────────────────────────────────

def _is_colab():
    try:
        import google.colab
        return True
    except ImportError:
        return False

if __name__ == '__main__':
    print("Chargement des données…")
    dl.load_data()
    print("Données chargées.")

    PORT = 5001

    if _is_colab():
        try:
            from pyngrok import ngrok
            public_url = ngrok.connect(PORT)
            print(f"\n✅ Application accessible sur : {public_url}\n")
        except Exception as e:
            print(f"⚠️  ngrok non disponible ({e}). Installe-le avec : !pip install pyngrok")
            print("   Puis relance la cellule.")
        app.run(port=PORT)
    else:
        print(f"Démarrage sur http://localhost:{PORT}")
        app.run(debug=True, port=PORT)
