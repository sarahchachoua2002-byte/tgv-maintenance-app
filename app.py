import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from data_loader import (
    load_data, get_sim_date, get_kpis, get_rames, get_rame_detail,
    get_planning, get_historique_mensuel, get_distribution_ecarts,
    get_repartition_flottes, train_model, predict_ecart,
    get_alertes, get_liste_rames, get_liste_operations
)
import pandas as pd

app = Flask(__name__)
app.secret_key = 'tgv_maintenance_2026'

# Chargement des données au démarrage (fonctionne avec gunicorn et python app.py)
load_data()
train_model()

USERS = {
    'user': {'password': 'user', 'role': 'Programmeur', 'nom': 'Utilisateur'},
}


@app.before_request
def require_login():
    public = ['login', 'static']
    if request.endpoint and request.endpoint not in public and 'user' not in session:
        return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username in USERS and USERS[username]['password'] == password:
            session['user'] = {
                'username': username,
                'role': USERS[username]['role'],
                'nom': USERS[username]['nom'],
            }
            return redirect(url_for('dashboard'))
        error = "Identifiants incorrects. Réessayez."
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    kpis    = get_kpis()
    alertes = get_alertes()
    return render_template('dashboard.html', kpis=kpis, alertes=alertes)


@app.route('/parc')
def parc():
    rames   = get_rames()
    flottes = sorted(rames['flotte'].unique().tolist())
    return render_template('parc.html', rames=rames.to_dict('records'), flottes=flottes)


@app.route('/rame/<n_rame>')
def rame_detail(n_rame):
    df_r = get_rame_detail(n_rame)
    if df_r.empty:
        return redirect(url_for('parc'))

    info = {
        'n_rame':    n_rame,
        'flotte':    df_r['flotte'].iloc[0],
        'categorie': df_r['categorie'].iloc[0],
        'nb_ops':    len(df_r),
        'ecart_moy': round(float(df_r['ecart_debut_h'].mean()), 1),
        'taux_retard': round(float((df_r['ecart_debut_h'] > 0).mean() * 100), 1),
        'taux_nc':   round(float((df_r['ecart_butee_h'] > 0).mean() * 100), 1)
                     if df_r['ecart_butee_h'].notna().any() else 0,
    }

    ops = df_r[['code_op', 'debut_planifie', 'debut_reel', 'fin_reelle',
                 'ecart_debut_h', 'ecart_butee_h', 'duree_reelle_h',
                 'statut_conformite']].copy()
    ops['debut_planifie'] = ops['debut_planifie'].dt.strftime('%d/%m/%Y %H:%M')
    ops['debut_reel']     = ops['debut_reel'].dt.strftime('%d/%m/%Y %H:%M')
    ops['fin_reelle']     = ops['fin_reelle'].dt.strftime('%d/%m/%Y %H:%M')
    ops = ops.fillna('—')

    return render_template('rame.html', info=info, ops=ops.to_dict('records'))


@app.route('/planning')
def planning():
    sim_date = get_sim_date()
    df_plan, sem_start, sem_end = get_planning(sim_date, nb_semaines=3)

    events = []
    for _, row in df_plan.iterrows():
        statut = row.get('statut_conformite', 'conforme')
        color_map = {
            'conforme':     '#28a745',
            'non_conforme': '#dc3545',
            'retard':       '#fd7e14',
            'avance':       '#17a2b8',
        }
        color = color_map.get(statut, '#6c757d')
        events.append({
            'title': f"Rame {row['n__rame']} — {row['code_op']}",
            'start': row['debut_planifie'].isoformat() if pd.notna(row['debut_planifie']) else None,
            'end':   row['fin_reelle'].isoformat() if pd.notna(row['fin_reelle']) else None,
            'color': color,
            'extendedProps': {
                'rame':   row['n__rame'],
                'op':     row['code_op'],
                'ecart':  round(float(row['ecart_debut_h']), 1),
                'statut': statut,
            }
        })
    events = [e for e in events if e['start']]

    return render_template('planning.html',
                           events=events,
                           sim_date=sim_date.strftime('%d/%m/%Y'),
                           sim_semaine=f"S{sim_date.isocalendar()[1]} {sim_date.year}")


@app.route('/historique')
def historique():
    hist   = get_historique_mensuel()
    flottes= get_repartition_flottes()
    return render_template('historique.html',
                           hist=hist.to_dict('records'),
                           flottes=flottes.to_dict('records'))


@app.route('/prediction', methods=['GET', 'POST'])
def prediction():
    rames = get_liste_rames()
    result = None
    form_data = {}

    if request.method == 'POST':
        n_rame      = request.form.get('n_rame', '')
        code_op     = request.form.get('code_op', '')
        date_planif = request.form.get('date_planif', '')
        duree_prev  = float(request.form.get('duree_prev', 8))
        form_data   = {'n_rame': n_rame, 'code_op': code_op,
                       'date_planif': date_planif, 'duree_prev': duree_prev}
        try:
            result = predict_ecart(n_rame, code_op, date_planif, duree_prev)
        except Exception as e:
            result = {'error': str(e)}

    return render_template('prediction.html', rames=rames, result=result, form_data=form_data)


@app.route('/api/operations/<n_rame>')
def api_operations(n_rame):
    ops = get_liste_operations(n_rame)
    return jsonify(ops)


@app.route('/api/chart/historique')
def api_chart_historique():
    hist = get_historique_mensuel()
    return jsonify({
        'labels':       hist['mois_label'].tolist(),
        'ecart_moyen':  hist['ecart_moyen_h'].tolist(),
        'taux_retard':  hist['taux_retard_pct'].tolist(),
        'taux_nc':      hist['taux_nc_pct'].tolist(),
        'nb_inter':     hist['nb_interventions'].tolist(),
    })


@app.route('/api/chart/distribution')
def api_chart_distribution():
    vals = get_distribution_ecarts()
    # Créer des bins [-168, -120, ..., 120, 168]
    bins = list(range(-168, 169, 12))
    counts, edges = __import__('numpy').histogram(vals, bins=bins)
    labels = [f"{int(e)}" for e in edges[:-1]]
    return jsonify({'labels': labels, 'counts': counts.tolist()})


@app.route('/api/chart/flottes')
def api_chart_flottes():
    f = get_repartition_flottes()
    return jsonify({
        'labels':    f['flotte'].tolist(),
        'nb':        f['nb'].tolist(),
        'ecart_moy': f['ecart_moy'].tolist(),
        'taux_nc':   f['taux_nc'].tolist(),
    })


@app.route('/api/chart/rame/<n_rame>')
def api_chart_rame(n_rame):
    df_r = get_rame_detail(n_rame).sort_values('debut_planifie')
    labels = df_r['debut_planifie'].dt.strftime('%d/%m/%y').tolist()
    ecarts = df_r['ecart_debut_h'].round(1).tolist()
    return jsonify({'labels': labels, 'ecarts': ecarts})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
