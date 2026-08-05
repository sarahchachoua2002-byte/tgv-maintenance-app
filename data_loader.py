import pandas as pd
import numpy as np
import hashlib
import re
import os
import pickle
import json
from datetime import datetime, timedelta
from functools import lru_cache

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "..")
EXPORT_DIR = os.path.join(BASE_DIR, "data_export")
FILE_PROG = os.path.join(DATA_DIR, "dataProgone_S1-S12.xlsx")
FILE_REAL = os.path.join(DATA_DIR, "data_S1_S12 réalisation.xlsx")

_cache = {}

def clean_columns(df):
    cols = []
    for c in df.columns:
        c = str(c).strip()
        for src, dst in [('é','e'),('è','e'),('ê','e'),('ë','e'),('à','a'),('â','a'),
                         ('ä','a'),('î','i'),('ï','i'),('ô','o'),('ö','o'),('ù','u'),
                         ('û','u'),('ü','u'),('ç','c'),('ñ','n')]:
            c = c.replace(src, dst)
        c = re.sub(r'[^\w]', '_', c).lower().strip('_')
        cols.append(c)
    df.columns = cols
    return df

def anonymize(value):
    if pd.isna(value):
        return np.nan
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]

def _export_available():
    needed = ['df_merge.pkl', 'df_prog_unmatched.pkl',
              'df_prog_clean.pkl', 'df_real_clean.pkl']
    return all(os.path.exists(os.path.join(EXPORT_DIR, f)) for f in needed)


def load_data():
    if 'df_merge' in _cache:
        return _cache['df_prog'], _cache['df_real'], _cache['df_merge']

    # ── Chemin rapide : fichiers exportés depuis le notebook ──────────────────
    if _export_available():
        print("[data_loader] Chargement depuis data_export/ (notebook)")
        with open(os.path.join(EXPORT_DIR, 'df_prog_clean.pkl'),     'rb') as f: df_prog_clean     = pickle.load(f)
        with open(os.path.join(EXPORT_DIR, 'df_real_clean.pkl'),     'rb') as f: df_real_clean     = pickle.load(f)
        with open(os.path.join(EXPORT_DIR, 'df_merge.pkl'),          'rb') as f: df_merge          = pickle.load(f)
        with open(os.path.join(EXPORT_DIR, 'df_prog_unmatched.pkl'), 'rb') as f: df_prog_unmatched = pickle.load(f)

        # Colonnes requises par l'app
        if 'semaine_iso' not in df_merge.columns and 'debut_planifie' in df_merge.columns:
            df_merge['semaine_iso'] = df_merge['debut_planifie'].dt.isocalendar().week.astype(int)
        if 'semaine_iso' not in df_prog_unmatched.columns and 'debut_planifie' in df_prog_unmatched.columns:
            df_prog_unmatched['semaine_iso'] = df_prog_unmatched['debut_planifie'].dt.isocalendar().week.astype(int)
        if 'jour_semaine' not in df_merge.columns and 'debut_planifie' in df_merge.columns:
            df_merge['jour_semaine'] = df_merge['debut_planifie'].dt.dayofweek
        if 'statut_conformite' not in df_merge.columns:
            def _statut(row):
                eb = row.get('ecart_butee_h', np.nan)
                ed = row.get('ecart_debut_h', 0)
                if pd.notna(eb) and eb > 0: return 'non_conforme'
                if ed > 24:  return 'retard'
                if ed < -24: return 'avance'
                return 'conforme'
            df_merge['statut_conformite'] = df_merge.apply(_statut, axis=1)
        if 'match_fiable' not in df_merge.columns:
            df_merge['match_fiable'] = (
                df_merge['fin_reelle'].notna() & df_merge['debut_planifie'].notna() &
                (df_merge['fin_reelle'] >= df_merge['debut_planifie'])
            )

        _cache['df_prog']          = df_prog_clean
        _cache['df_real']          = df_real_clean
        _cache['df_merge']         = df_merge
        _cache['df_prog_unmatched']= df_prog_unmatched
        return df_prog_clean, df_real_clean, df_merge

    df_prog = clean_columns(pd.read_excel(FILE_PROG, sheet_name=0))
    df_real = clean_columns(pd.read_excel(FILE_REAL, sheet_name=0))

    # Dates PROGONE
    date_cols_p = [c for c in df_prog.columns if any(k in c for k in ['date','debut','fin','but','projection'])]
    for col in date_cols_p:
        df_prog[col] = pd.to_datetime(df_prog[col], errors='coerce')

    # Dates REALISATION
    date_cols_r = [c for c in df_real.columns if any(k in c for k in ['date','debut','fin'])]
    for col in date_cols_r:
        df_real[col] = pd.to_datetime(df_real[col], dayfirst=True, errors='coerce')

    df_prog = df_prog.drop_duplicates()
    df_real = df_real.drop_duplicates()

    # Anonymisation
    cols_anon = [c for c in df_prog.columns if any(k in c for k in ['createur','person','nom','prenom'])]
    for col in cols_anon:
        df_prog[col + "_anon"] = df_prog[col].apply(anonymize)
        df_prog.drop(columns=[col], inplace=True)

    # Colonnes de jointure
    debut_prog    = [c for c in df_prog.columns if 'projection' in c][0]
    col_code_prog = [c for c in df_prog.columns if 'code' in c and 'op' in c][0]
    col_code_real = [c for c in df_real.columns if 'code' in c and 'op' in c][0]
    col_flotte    = [c for c in df_prog.columns if 'flotte' in c and 'libelle' not in c][0]
    col_cat       = [c for c in df_prog.columns if 'cat' in c][0]
    col_butee     = next((c for c in df_prog.columns if 'but' in c and 'date' in c), None)

    df_prog['n__rame']      = df_prog['n__rame'].astype(str).str.strip()
    df_real['n_ef']         = df_real['n_ef'].astype(str).str.strip()
    df_prog[col_code_prog]  = df_prog[col_code_prog].astype(str).str.strip().str.upper()
    df_real[col_code_real]  = df_real[col_code_real].astype(str).str.strip().str.upper()

    df_prog_clean = df_prog.dropna(subset=[debut_prog]).copy()
    df_real_clean = df_real.dropna(subset=['debut_rdv', 'fin_rdv']).copy()

    # prog_j
    cols_pj = ['n__rame', col_code_prog, debut_prog, col_flotte, col_cat]
    if col_butee:
        cols_pj.append(col_butee)
    cols_pj = [c for c in cols_pj if c in df_prog_clean.columns]
    rename_p = {debut_prog: 'debut_planifie', col_flotte: 'flotte',
                col_cat: 'categorie', col_code_prog: 'code_op'}
    if col_butee:
        rename_p[col_butee] = 'date_butee'
    prog_j = df_prog_clean[cols_pj].rename(columns=rename_p)

    # libelle operation pour affichage
    col_lib = next((c for c in df_prog_clean.columns if 'libelle' in c and 'op' in c), None)
    if col_lib:
        prog_j = prog_j.join(df_prog_clean[[col_lib]].rename(columns={col_lib: 'libelle_operation'}))

    # statut rdv
    col_statut = next((c for c in df_prog_clean.columns if 'statut' in c and 'rdv' in c), None)
    if col_statut:
        prog_j = prog_j.join(df_prog_clean[[col_statut]].rename(columns={col_statut: 'statut_rdv'}))

    # real_j
    col_dp = next((c for c in df_real_clean.columns if 'debut' in c and 'prev' in c), None)
    col_fp = next((c for c in df_real_clean.columns if 'fin' in c and 'prev' in c), None)
    cols_rj = ['n_ef', col_code_real, 'debut_rdv', 'fin_rdv']
    rename_r = {'debut_rdv': 'debut_reel', 'fin_rdv': 'fin_reelle', col_code_real: 'code_op'}
    if col_dp:
        cols_rj.append(col_dp)
        rename_r[col_dp] = 'debut_previsionnel'
    if col_fp:
        cols_rj.append(col_fp)
        rename_r[col_fp] = 'fin_previsionnelle'

    # site realisation
    col_site = next((c for c in df_real_clean.columns if c == 'site'), None)
    if col_site:
        cols_rj.append(col_site)

    cols_rj = [c for c in cols_rj if c in df_real_clean.columns]
    real_j = df_real_clean[cols_rj].rename(columns=rename_r)

    # Restreindre PROGONE et RÉALISATION aux semaines S1-S12 (périmètre de l'extraction)
    prog_j = prog_j.copy()
    prog_j['_sem']  = prog_j['debut_planifie'].dt.isocalendar().week.astype(int)
    prog_j['_year'] = prog_j['debut_planifie'].dt.year
    prog_j = prog_j[prog_j['_sem'].between(1, 12) & (prog_j['_year'] == 2026)].drop(columns=['_sem', '_year'])

    real_j = real_j.copy()
    real_j['_sem']  = real_j['debut_reel'].dt.isocalendar().week.astype(int)
    real_j['_year'] = real_j['debut_reel'].dt.year
    real_j = real_j[real_j['_sem'].between(1, 12) & (real_j['_year'] == 2026)].drop(columns=['_sem', '_year'])

    # Matching 1-à-1 glouton ±7j par INDEX ENTIER (évite les bugs de précision datetime string)
    prog_j = prog_j.reset_index(drop=True)
    real_j = real_j.reset_index(drop=True)

    df_cross = pd.merge(
        prog_j.assign(_pi=prog_j.index),
        real_j.assign(_ri=real_j.index),
        left_on=['n__rame', 'code_op'],
        right_on=['n_ef', 'code_op'],
        how='inner'
    )

    df_cross['_ecart_abs'] = (
        df_cross['debut_reel'] - df_cross['debut_planifie']
    ).dt.total_seconds().abs()

    df_cross = df_cross[df_cross['_ecart_abs'] <= 7 * 24 * 3600].sort_values('_ecart_abs').reset_index(drop=True)

    used_p, used_r, matched_pi = set(), set(), set()
    for _, row in df_cross.iterrows():
        pi, ri = int(row['_pi']), int(row['_ri'])
        if pi not in used_p and ri not in used_r:
            used_p.add(pi); used_r.add(ri); matched_pi.add(pi)

    matched_idx = df_cross[df_cross['_pi'].isin(matched_pi)].drop_duplicates('_pi').index.tolist()

    df_merge = df_cross.loc[matched_idx].drop(columns=['_ecart_abs', '_pi', '_ri']).copy()

    # matched_prog_indices = ensemble des index entiers de prog_j matchés
    matched_prog_indices = matched_pi

    # ── Second passage : matching catégorie MODULE (fenêtre 7 jours, code libre) ──
    # Justification : pour MODULE, une opération MLFAM peut être réalisée comme MLFB-
    # (même visite, codes légèrement différents). On matche sur (rame, catégorie MODULE,
    # présence d'une réalisation MODULE dans la même semaine de 7 jours).
    CATS_LARGE_WINDOW = {'MODULE': 35}
    col_cat_real = next((c for c in df_prog.columns if 'cat' in c), None)

    # Identifier les RÉALISATION de catégorie MODULE (codes commençant par M)
    real_module = real_j[real_j['code_op'].str.upper().str.startswith('M')].copy()
    real_module['_key_real2'] = (
        real_module['n_ef'].astype(str) + '||' +
        real_module['debut_reel'].dt.strftime('%Y-%m-%d %H:%M:%S')
    )

    # PROGONE MODULE non encore matchées (second passage, index entier)
    prog_module_nm = prog_j[
        (~prog_j.index.isin(matched_prog_indices)) &
        (prog_j['categorie'] == 'MODULE')
    ].copy()

    extra_rows = []
    max_sec_mod = 7 * 24 * 3600
    for pidx, prow in prog_module_nm.iterrows():
        rame = str(prow['n__rame'])
        candidates = real_module[real_module['n_ef'].astype(str) == rame].copy()
        candidates['_ea'] = (candidates['debut_reel'] - prow['debut_planifie']).dt.total_seconds().abs()
        candidates = candidates[candidates['_ea'] <= max_sec_mod].sort_values('_ea')
        for _, rrow in candidates.iterrows():
            kr2 = rrow['_key_real2']
            if pidx not in matched_prog_indices and kr2 not in used_r:
                merged_row = {**prow.to_dict(), **rrow.to_dict()}
                merged_row['n__rame']        = rame
                merged_row['debut_planifie'] = prow['debut_planifie']
                merged_row['debut_reel']     = rrow['debut_reel']
                merged_row['fin_reelle']     = rrow['fin_reelle']
                merged_row['code_op']        = prow['code_op']
                extra_rows.append(merged_row)
                matched_prog_indices.add(pidx)
                used_r.add(kr2)
                break

    if extra_rows:
        df_extra = pd.DataFrame(extra_rows)
        common_cols = [c for c in df_merge.columns if c in df_extra.columns]
        df_merge = pd.concat([df_merge, df_extra[common_cols]], ignore_index=True)

    # PROGONE non matchées — via index entier (cohérent avec notebook)
    df_prog_unmatched = prog_j[~prog_j.index.isin(matched_prog_indices)].copy()
    df_prog_unmatched['semaine_iso'] = df_prog_unmatched['debut_planifie'].dt.isocalendar().week.astype(int)

    # Indicateurs
    df_merge['ecart_debut_h']  = (df_merge['debut_reel'] - df_merge['debut_planifie']).dt.total_seconds() / 3600
    df_merge['duree_reelle_h'] = (df_merge['fin_reelle'] - df_merge['debut_reel']).dt.total_seconds() / 3600

    if 'fin_previsionnelle' in df_merge.columns:
        df_merge['fin_previsionnelle'] = pd.to_datetime(df_merge['fin_previsionnelle'], errors='coerce')
        df_merge['ecart_fin_h'] = (df_merge['fin_reelle'] - df_merge['fin_previsionnelle']).dt.total_seconds() / 3600
    else:
        df_merge['ecart_fin_h'] = np.nan

    if 'debut_previsionnel' in df_merge.columns and 'fin_previsionnelle' in df_merge.columns:
        df_merge['debut_previsionnel'] = pd.to_datetime(df_merge['debut_previsionnel'], errors='coerce')
        df_merge['duree_previsionnelle_h'] = (df_merge['fin_previsionnelle'] - df_merge['debut_previsionnel']).dt.total_seconds() / 3600
        df_merge['ecart_duree_h'] = df_merge['duree_reelle_h'] - df_merge['duree_previsionnelle_h']
    else:
        df_merge['duree_previsionnelle_h'] = np.nan
        df_merge['ecart_duree_h'] = np.nan

    if col_butee:
        df_merge['date_butee'] = pd.to_datetime(df_merge['date_butee'], errors='coerce')
        df_merge['ecart_butee_h'] = (df_merge['debut_reel'] - df_merge['date_butee']).dt.total_seconds() / 3600
    else:
        df_merge['ecart_butee_h'] = np.nan

    # Supprimer les lignes sans écart calculable
    df_merge = df_merge.dropna(subset=['ecart_debut_h']).copy()

    # Fiabilité du matching : si l'opération est terminée avant la date planifiée
    # → cycles différents, PROGONE ne conserve plus la planification originale
    df_merge['match_fiable'] = (
        df_merge['fin_reelle'].notna() &
        df_merge['debut_planifie'].notna() &
        (df_merge['fin_reelle'] >= df_merge['debut_planifie'])
    )

    # Features temporelles
    df_merge['mois']         = df_merge['debut_planifie'].dt.month
    df_merge['jour_semaine'] = df_merge['debut_planifie'].dt.dayofweek
    df_merge['trimestre']    = df_merge['debut_planifie'].dt.quarter
    df_merge['semaine_iso']  = df_merge['debut_planifie'].dt.isocalendar().week.astype(int)
    df_merge['annee']        = df_merge['debut_planifie'].dt.year

    # Statut conformite
    def statut(row):
        if pd.isna(row['ecart_butee_h']):
            if row['ecart_debut_h'] > 24:
                return 'retard'
            elif row['ecart_debut_h'] < -24:
                return 'avance'
            return 'conforme'
        if row['ecart_butee_h'] > 0:
            return 'non_conforme'
        if row['ecart_debut_h'] > 24:
            return 'retard'
        if row['ecart_debut_h'] < -24:
            return 'avance'
        return 'conforme'

    df_merge['statut_conformite'] = df_merge.apply(statut, axis=1)

    _cache['df_prog'] = df_prog_clean
    _cache['df_real'] = df_real_clean
    _cache['df_merge'] = df_merge
    _cache['df_prog_unmatched'] = df_prog_unmatched
    return df_prog_clean, df_real_clean, df_merge


def get_sim_date():
    """Date de simulation = semaine la plus chargée dans les données."""
    _, _, df = load_data()
    # Prendre la semaine avec le plus d'opérations planifiées
    semaines = df.groupby(df['debut_planifie'].dt.to_period('W')).size()
    best = semaines.idxmax().start_time
    return best


def get_kpis(sim_date=None):
    _, _, df = load_data()
    if sim_date is None:
        sim_date = get_sim_date()

    sem_start = sim_date - timedelta(days=sim_date.weekday())
    sem_end   = sem_start + timedelta(days=6)

    df_sem = df[(df['debut_planifie'] >= sem_start) & (df['debut_planifie'] <= sem_end)]

    total      = len(df)
    nb_sem     = len(df_sem)
    ecart_moy  = round(df['ecart_debut_h'].mean(), 1)
    taux_retard= round((df['ecart_debut_h'] > 0).mean() * 100, 1)
    taux_nc    = round((df['ecart_butee_h'] > 0).mean() * 100, 1) if df['ecart_butee_h'].notna().any() else 0
    nb_nc_sem  = int((df_sem['statut_conformite'] == 'non_conforme').sum())

    return {
        'total_operations': total,
        'nb_operations_semaine': nb_sem,
        'ecart_moyen_h': ecart_moy,
        'taux_retard_pct': taux_retard,
        'taux_nonconformite_pct': taux_nc,
        'nb_nonconformes_semaine': nb_nc_sem,
        'sim_date': sem_start.strftime('%d/%m/%Y'),
        'sim_semaine': f"S{sem_start.isocalendar()[1]} {sem_start.year}",
    }


def get_rames():
    _, _, df = load_data()
    rames = df.groupby('n__rame').agg(
        flotte=('flotte', 'first'),
        nb_operations=('ecart_debut_h', 'count'),
        ecart_moyen=('ecart_debut_h', 'mean'),
        taux_retard=('ecart_debut_h', lambda x: (x > 0).mean() * 100),
        nb_nonconformes=('statut_conformite', lambda x: (x == 'non_conforme').sum()),
        derniere_op=('debut_reel', 'max'),
        prochaine_planif=('debut_planifie', lambda x: x[x > get_sim_date()].min() if any(x > get_sim_date()) else pd.NaT),
    ).reset_index()
    rames['ecart_moyen']  = rames['ecart_moyen'].round(1)
    rames['taux_retard']  = rames['taux_retard'].round(1)

    def statut_rame(row):
        if row['nb_nonconformes'] > 0:
            return 'non_conforme'
        if row['taux_retard'] > 50:
            return 'a_surveiller'
        return 'conforme'

    rames['statut'] = rames.apply(statut_rame, axis=1)
    return rames.sort_values('nb_nonconformes', ascending=False)


def get_rame_detail(n_rame):
    _, _, df = load_data()
    df_r = df[df['n__rame'] == str(n_rame)].sort_values('debut_planifie', ascending=False).copy()
    return df_r


def get_planning(sim_date=None, nb_semaines=2):
    _, _, df = load_data()
    if sim_date is None:
        sim_date = get_sim_date()

    sem_start = sim_date - timedelta(days=sim_date.weekday())
    sem_end   = sem_start + timedelta(weeks=nb_semaines, days=6)

    df_plan = df[(df['debut_planifie'] >= sem_start) & (df['debut_planifie'] <= sem_end)].copy()
    return df_plan, sem_start, sem_end


def get_historique_mensuel():
    _, _, df = load_data()
    df = df.copy()
    df['mois_label'] = df['debut_planifie'].dt.to_period('M').astype(str)
    hist = df.groupby('mois_label').agg(
        nb_interventions=('ecart_debut_h', 'count'),
        ecart_moyen_h=('ecart_debut_h', 'mean'),
        taux_retard_pct=('ecart_debut_h', lambda x: (x > 0).mean() * 100),
        taux_nc_pct=('ecart_butee_h', lambda x: (x > 0).mean() * 100 if x.notna().any() else 0),
    ).reset_index()
    hist['ecart_moyen_h']   = hist['ecart_moyen_h'].round(1)
    hist['taux_retard_pct'] = hist['taux_retard_pct'].round(1)
    hist['taux_nc_pct']     = hist['taux_nc_pct'].round(1)
    return hist


def get_distribution_ecarts():
    _, _, df = load_data()
    vals = df['ecart_debut_h'].clip(-168, 168).dropna().tolist()
    return vals


def get_repartition_flottes():
    _, _, df = load_data()
    r = df.groupby('flotte').agg(
        nb=('ecart_debut_h', 'count'),
        ecart_moy=('ecart_debut_h', 'mean'),
        taux_nc=('ecart_butee_h', lambda x: (x > 0).mean() * 100 if x.notna().any() else 0),
    ).reset_index()
    r['ecart_moy'] = r['ecart_moy'].round(1)
    r['taux_nc']   = r['taux_nc'].round(1)
    return r


def train_classification_model():
    """Modèle 2 : prédit si une opération planifiée sera réalisée (1) ou non (0)."""
    if 'model_clf' in _cache:
        return _cache['model_clf'], _cache['clf_features']

    # ── Chemin rapide : modèle exporté depuis le notebook ────────────────────
    clf_pkl   = os.path.join(EXPORT_DIR, 'clf.pkl')
    meta_json = os.path.join(EXPORT_DIR, 'model_meta.json')
    enc_pkl   = os.path.join(EXPORT_DIR, 'encoders.pkl')
    base_pkl  = os.path.join(EXPORT_DIR, 'base_clf.pkl')

    if all(os.path.exists(p) for p in [clf_pkl, meta_json, enc_pkl]):
        print("[data_loader] Modèle chargé depuis data_export/ (notebook)")
        with open(clf_pkl,   'rb') as f: clf      = pickle.load(f)
        with open(enc_pkl,   'rb') as f: encoders = pickle.load(f)
        with open(meta_json, 'r', encoding='utf-8') as f: meta = json.load(f)

        features_clf = meta['features']
        _cache['model_clf']       = clf
        _cache['clf_features']    = features_clf
        _cache['clf_accuracy']    = meta['accuracy']
        _cache['clf_importances'] = [(d['feature'], d['value']/100) for d in meta['importances']]
        _cache['le_cat2']         = encoders.get('le_cat')
        _cache['le_flotte2']      = encoders.get('le_flt')
        _cache['le_code2']        = encoders.get('le_cod')
        _cache['le_catflotte']    = encoders.get('le_cf')
        _cache['le_site2']        = encoders.get('le_site')
        if os.path.exists(base_pkl):
            with open(base_pkl, 'rb') as f: _cache['base_clf'] = pickle.load(f)
        taux_path = os.path.join(EXPORT_DIR, 'taux_hist.json')
        if os.path.exists(taux_path):
            with open(taux_path, 'r', encoding='utf-8') as f:
                th = json.load(f)
            _cache['taux_cat_dict']   = th.get('taux_cat', {})
            _cache['taux_code_dict']  = th.get('taux_code', {})
            _cache['charge_sem_dict'] = {int(k): v for k, v in th.get('charge_sem', {}).items()}
        return clf, features_clf

    from xgboost import XGBClassifier
    from sklearn.preprocessing import LabelEncoder
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    load_data()
    df_merge   = _cache['df_merge']
    df_unmatched = _cache['df_prog_unmatched']

    import holidays
    fr_holidays = holidays.France(years=[2025, 2026])

    def is_ferie(date):
        try:
            return 1 if date.date() in fr_holidays else 0
        except Exception:
            return 0

    # Dataset : matchées = 1, non-matchées = 0
    df_pos = df_merge[['n__rame','code_op','categorie','flotte','semaine_iso','jour_semaine']].copy()
    df_pos['site']      = df_merge['site'].fillna('Inconnu') if 'site' in df_merge.columns else 'Inconnu'
    df_pos['jour_ferie'] = df_merge['debut_planifie'].apply(is_ferie)
    df_pos['realise']   = 1

    df_neg = df_unmatched[['n__rame','code_op','categorie','flotte','semaine_iso']].copy()
    df_neg['jour_semaine'] = df_unmatched['debut_planifie'].dt.dayofweek
    df_neg['jour_ferie']   = df_unmatched['debut_planifie'].apply(is_ferie)
    df_neg['site']    = 'Inconnu'
    df_neg['realise'] = 0

    df_clf = pd.concat([df_pos, df_neg], ignore_index=True)
    df_clf = df_clf.dropna(subset=['categorie','flotte','semaine_iso'])

    le_cat2   = LabelEncoder()
    le_flotte2= LabelEncoder()
    le_code2  = LabelEncoder()
    le_site2  = LabelEncoder()

    df_clf['categorie_enc'] = le_cat2.fit_transform(df_clf['categorie'].astype(str))
    df_clf['flotte_enc']    = le_flotte2.fit_transform(df_clf['flotte'].astype(str))
    df_clf['code_enc']      = le_code2.fit_transform(df_clf['code_op'].astype(str))
    df_clf['site_enc']      = le_site2.fit_transform(df_clf['site'].astype(str))

    # Taux historique par catégorie et code (sur tout le dataset — sans leakage car pas lié au site)
    taux_cat  = df_clf.groupby('categorie')['realise'].mean().rename('taux_hist_cat')
    df_clf    = df_clf.merge(taux_cat, on='categorie', how='left')

    taux_code = df_clf.groupby('code_op')['realise'].mean().rename('taux_hist_code')
    df_clf    = df_clf.merge(taux_code, on='code_op', how='left')

    # Charge de la semaine (comptage, pas de target leakage)
    charge_sem = df_clf.groupby('semaine_iso')['realise'].count().rename('charge_semaine')
    df_clf     = df_clf.merge(charge_sem, on='semaine_iso', how='left')

    # Interaction catégorie × flotte
    df_clf['cat_flotte'] = df_clf['categorie'].astype(str) + '_' + df_clf['flotte'].astype(str)
    le_catflotte = LabelEncoder()
    df_clf['cat_flotte_enc'] = le_catflotte.fit_transform(df_clf['cat_flotte'].astype(str))

    features_clf = [
        'categorie_enc', 'flotte_enc', 'code_enc',
        'jour_semaine', 'jour_ferie', 'taux_hist_cat', 'taux_hist_code',
        'charge_semaine', 'cat_flotte_enc'
    ]
    X = df_clf[features_clf].fillna(0)
    y = df_clf['realise']

    # Split stratifié
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    n0 = int((y_train == 0).sum())
    n1 = int((y_train == 1).sum())
    spw = round(n0 / n1, 2)

    base_clf = XGBClassifier(
        n_estimators=300, learning_rate=0.05, max_depth=4,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=spw,
        random_state=42, eval_metric='logloss',
        verbosity=0, use_label_encoder=False
    )
    base_clf.fit(X_train, y_train)
    importances = base_clf.feature_importances_.tolist()

    # Calibration sigmoid (cohérent avec le notebook)
    clf = CalibratedClassifierCV(base_clf, method='sigmoid', cv=3)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = round(float(accuracy_score(y_test, y_pred)) * 100, 1)

    _cache['model_clf']    = clf
    _cache['clf_features'] = features_clf
    _cache['le_cat2']      = le_cat2
    _cache['le_flotte2']   = le_flotte2
    _cache['le_code2']     = le_code2
    _cache['le_site2']     = le_site2
    _cache['le_catflotte'] = le_catflotte
    _cache['clf_accuracy'] = acc
    _cache['clf_importances'] = list(zip(features_clf, importances))

    return clf, features_clf


def train_model():
    if 'model' in _cache:
        return _cache['model'], _cache['model_features']

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import mean_squared_error, mean_absolute_error

    _, _, df = load_data()
    df = df[df['match_fiable'] == True].copy()

    df['mois_sin'] = np.sin(2 * np.pi * df['mois'] / 12)
    df['mois_cos'] = np.cos(2 * np.pi * df['mois'] / 12)
    df['jour_sin'] = np.sin(2 * np.pi * df['jour_semaine'] / 7)
    df['jour_cos'] = np.cos(2 * np.pi * df['jour_semaine'] / 7)

    le_cat   = LabelEncoder()
    le_flotte= LabelEncoder()
    df['categorie_enc'] = le_cat.fit_transform(df['categorie'].astype(str))
    df['flotte_enc']    = le_flotte.fit_transform(df['flotte'].astype(str))

    features = ['mois_sin', 'mois_cos', 'jour_sin', 'jour_cos', 'categorie_enc', 'flotte_enc']

    X = df[features].fillna(0)
    y = df['ecart_debut_h']

    from sklearn.model_selection import train_test_split as tts
    X_train, X_test, y_train, y_test = tts(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingRegressor(n_estimators=100, learning_rate=0.05,
                                       max_depth=4, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    rmse = round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 1)
    mae  = round(float(mean_absolute_error(y_test, y_pred)), 1)
    r2   = round(float(1 - np.sum((y_test - y_pred)**2) / np.sum((y_test - y_test.mean())**2)), 3)

    _cache['model']            = model
    _cache['model_features']   = features
    _cache['le_cat']           = le_cat
    _cache['le_flotte']        = le_flotte
    _cache['reg_rmse']         = rmse
    _cache['reg_mae']          = mae
    _cache['reg_r2']           = r2
    _cache['reg_importances']  = list(zip(features, model.feature_importances_.tolist()))
    return model, features


def predict_ecart_simple(categorie, flotte, duree_prev_h=8.0):
    """Prédit l'écart en heures à partir de catégorie + flotte + durée prévisionnelle."""
    train_model()
    model   = _cache['model']
    le_cat  = _cache['le_cat']
    le_flt  = _cache['le_flotte']
    try:
        cat_enc = le_cat.transform([str(categorie)])[0]
    except Exception:
        cat_enc = 0
    try:
        flt_enc = le_flt.transform([str(flotte)])[0]
    except Exception:
        flt_enc = 0
    X = [[duree_prev_h, cat_enc, flt_enc]]
    return round(float(model.predict(X)[0]), 1)


def predict_ecart(n_rame, code_op, date_planif_str, duree_prev_h=8.0):
    _, _, df = load_data()
    model, features = train_model()

    date_planif = pd.to_datetime(date_planif_str)

    # Récupérer flotte et categorie de la rame
    rame_data = df[df['n__rame'] == str(n_rame)]
    flotte    = rame_data['flotte'].iloc[0] if len(rame_data) else 'Inconnu'
    categorie = rame_data[rame_data['code_op'] == str(code_op).upper()]['categorie'].iloc[0] \
                if len(rame_data[rame_data['code_op'] == str(code_op).upper()]) else \
                rame_data['categorie'].iloc[0] if len(rame_data) else 'Inconnu'

    le_cat    = _cache.get('le_cat')
    le_flotte = _cache.get('le_flotte')

    mois   = date_planif.month
    jour   = date_planif.dayofweek
    trim   = date_planif.quarter
    sem    = date_planif.isocalendar()[1]

    try:
        cat_enc    = le_cat.transform([categorie])[0]
    except Exception:
        cat_enc = 0
    try:
        flotte_enc = le_flotte.transform([flotte])[0]
    except Exception:
        flotte_enc = 0

    X_pred = np.array([[
        np.sin(2*np.pi*mois/12), np.cos(2*np.pi*mois/12),
        np.sin(2*np.pi*jour/7),  np.cos(2*np.pi*jour/7),
        cat_enc, flotte_enc
    ]])

    ecart_predit = float(model.predict(X_pred)[0])

    # Historique rame pour calculer taux NC
    if len(rame_data) > 0:
        taux_nc_rame = float((rame_data['ecart_butee_h'] > 0).mean() * 100) if rame_data['ecart_butee_h'].notna().any() else 0.0
        ecart_hist   = float(rame_data['ecart_debut_h'].mean())
    else:
        taux_nc_rame = 0.0
        ecart_hist   = 0.0

    # Risque NC estimé (heuristique)
    risque_nc = min(95, max(5, taux_nc_rame + (ecart_predit / 24) * 10))

    return {
        'ecart_predit_h': round(ecart_predit, 1),
        'risque_nc_pct':  round(risque_nc, 1),
        'flotte':         flotte,
        'categorie':      categorie,
        'date_planif':    date_planif.strftime('%d/%m/%Y'),
        'ecart_hist_moy': round(ecart_hist, 1),
        'recommandation': _recommandation(ecart_predit, risque_nc),
    }


def _recommandation(ecart_h, risque_nc):
    if risque_nc > 60:
        return f"⚠️ Risque élevé de non-conformité. Anticiper l'opération de {abs(ecart_h):.0f}h si possible."
    if ecart_h > 48:
        return f"📅 Retard probable de {ecart_h:.0f}h — revoir le créneau ou mobiliser des ressources supplémentaires."
    if ecart_h > 0:
        return f"⏱ Léger retard prévu ({ecart_h:.0f}h) — surveiller l'avancement."
    if ecart_h < -24:
        return f"✅ Opération prévue en avance de {abs(ecart_h):.0f}h — planning favorable."
    return "✅ Opération dans les délais prévus. Aucune action corrective nécessaire."


def get_alertes(sim_date=None):
    _, _, df = load_data()
    if sim_date is None:
        sim_date = get_sim_date()

    future = df[df['debut_planifie'] > sim_date].copy()
    alertes = []

    # Non-conformes historiques proches
    nc = df[df['statut_conformite'] == 'non_conforme'].sort_values('debut_reel', ascending=False).head(5)
    for _, row in nc.iterrows():
        alertes.append({
            'type': 'danger',
            'icone': '🚨',
            'titre': f"Non-conformité — Rame {row['n__rame']}",
            'detail': f"Op. {row['code_op']} — écart butée: +{row['ecart_butee_h']:.0f}h",
        })

    # Opérations planifiées bientôt
    soon = future[future['debut_planifie'] <= sim_date + timedelta(days=7)].head(3)
    for _, row in soon.iterrows():
        alertes.append({
            'type': 'warning',
            'icone': '📅',
            'titre': f"Opération imminente — Rame {row['n__rame']}",
            'detail': f"Op. {row['code_op']} prévue le {row['debut_planifie'].strftime('%d/%m/%Y')}",
        })

    return alertes[:8]


def get_planning_data():
    load_data()
    df_merge = _cache['df_merge']
    df_unmatched = _cache['df_prog_unmatched']

    df_fiable = df_merge[df_merge['match_fiable'] == True].copy()

    # Totaux globaux (fiable + non-fiable = toutes les ops matchées)
    nb_planifie    = len(df_merge) + len(df_unmatched)
    nb_realise     = len(df_merge)
    nb_non_realise = len(df_unmatched)
    taux_realisation = round(nb_realise / nb_planifie * 100, 1) if nb_planifie > 0 else 0.0

    # Par semaine
    sem_real = df_merge.groupby('semaine_iso').size().rename('realise')
    sem_unmatched = df_unmatched.groupby('semaine_iso').size().rename('non_realise')

    all_sems = sorted(set(df_merge['semaine_iso'].tolist() + df_unmatched['semaine_iso'].tolist()))
    sem_data = []
    for s in all_sems:
        r = int(sem_real.get(s, 0))
        nr = int(sem_unmatched.get(s, 0))
        total = r + nr
        sem_data.append({
            'sem': f'S{s}',
            'planifie': total,
            'realise': r,
            'non_realise': nr,
            'taux': round(r / total * 100, 1) if total > 0 else 0.0,
        })

    # Par catégorie
    cat_real = df_merge.groupby('categorie').size().rename('realise')
    cat_unmatched = df_unmatched.groupby('categorie').size().rename('non_realise')
    all_cats = sorted(set(df_merge['categorie'].dropna().tolist() + df_unmatched['categorie'].dropna().tolist()))
    cat_data = []
    for c in all_cats:
        r = int(cat_real.get(c, 0))
        nr = int(cat_unmatched.get(c, 0))
        total = r + nr
        cat_data.append({
            'categorie': c,
            'planifie': total,
            'realise': r,
            'non_realise': nr,
            'taux': round(r / total * 100, 1) if total > 0 else 0.0,
        })
    cat_data.sort(key=lambda x: x['taux'])

    # Opérations non réalisées (tableau)
    ops_nr = []
    for _, row in df_unmatched.sort_values('debut_planifie').iterrows():
        ops_nr.append({
            'n_rame':      row['n__rame'],
            'code_op':     row['code_op'],
            'categorie':   row.get('categorie', '—'),
            'semaine':     int(row['semaine_iso']) if pd.notna(row.get('semaine_iso')) else '—',
            'debut_planifie': row['debut_planifie'].strftime('%d/%m/%Y') if pd.notna(row['debut_planifie']) else '—',
            'date_butee':  row['date_butee'].strftime('%d/%m/%Y') if 'date_butee' in row and pd.notna(row.get('date_butee')) else '—',
        })

    return {
        'nb_planifie': nb_planifie,
        'nb_realise': nb_realise,
        'nb_non_realise': nb_non_realise,
        'taux_realisation': taux_realisation,
        'sem_data': sem_data,
        'cat_data': cat_data,
        'ops_nr': ops_nr,
    }


def get_liste_rames():
    _, _, df = load_data()
    return sorted(df['n__rame'].unique().tolist())


def get_ecart_historique(categorie=None, code_op=None, n_rame=None):
    """Écart moyen historique avec fallback progressif.
    Retourne (ecart_moy_h, nb_obs, niveau)."""
    load_data()
    df = _cache.get('df_merge', pd.DataFrame())
    if df.empty or 'ecart_debut_h' not in df.columns:
        return None, 0, 'aucune donnée'

    def _stat(sub):
        sub = sub.dropna(subset=['ecart_debut_h'])
        nb = len(sub)
        if nb == 0:
            return None, 0
        return round(float(sub['ecart_debut_h'].mean()), 1), nb

    # Niveau 1 : rame + catégorie + code_op
    if n_rame and categorie and code_op:
        mask = ((df['n__rame'].astype(str) == str(n_rame)) &
                (df['categorie'] == categorie) &
                (df['code_op'].astype(str).str.upper() == code_op.upper()))
        ecart, nb = _stat(df[mask])
        if nb >= 3:
            return ecart, nb, 'rame + catégorie + opération'

    # Niveau 2 : catégorie + code_op
    if categorie and code_op:
        mask = ((df['categorie'] == categorie) &
                (df['code_op'].astype(str).str.upper() == code_op.upper()))
        ecart, nb = _stat(df[mask])
        if nb >= 3:
            return ecart, nb, 'catégorie + opération'

    # Niveau 3 : catégorie seule
    if categorie:
        mask = df['categorie'] == categorie
        ecart, nb = _stat(df[mask])
        if nb >= 3:
            return ecart, nb, 'catégorie'

    return None, 0, 'aucune donnée'


def get_taux_realisation_historique(site=None, categorie=None, code_op=None):
    """Taux de réalisation historique avec fallback progressif.
    Retourne (taux_pct, nb_obs, niveau) où niveau indique la granularité utilisée."""
    load_data()
    df_merge     = _cache.get('df_merge', pd.DataFrame())
    df_unmatched = _cache.get('df_prog_unmatched', pd.DataFrame())

    def _taux(mask_m, mask_u):
        nb_realise  = int(mask_m.sum())
        nb_total    = nb_realise + int(mask_u.sum())
        if nb_total == 0:
            return None, 0
        return round(nb_realise / nb_total * 100, 1), nb_total

    # Niveau 1 : site + catégorie + code_op
    if site and categorie and code_op:
        has_site_m = 'site' in df_merge.columns
        has_site_u = 'site' in df_unmatched.columns
        mm = (df_merge['categorie'] == categorie) & (df_merge['code_op'].astype(str).str.upper() == code_op.upper())
        mu = (df_unmatched['categorie'] == categorie) & (df_unmatched['code_op'].astype(str).str.upper() == code_op.upper())
        if has_site_m:
            mm &= df_merge['site'].astype(str) == site
        if has_site_u:
            mu &= df_unmatched['site'].astype(str) == site
        taux, nb = _taux(mm, mu)
        if nb >= 5:
            return taux, nb, 'site + catégorie + opération'

    # Niveau 2 : site + catégorie
    if site and categorie:
        has_site_m = 'site' in df_merge.columns
        has_site_u = 'site' in df_unmatched.columns
        mm = df_merge['categorie'] == categorie
        mu = df_unmatched['categorie'] == categorie
        if has_site_m:
            mm &= df_merge['site'].astype(str) == site
        if has_site_u:
            mu &= df_unmatched['site'].astype(str) == site
        taux, nb = _taux(mm, mu)
        if nb >= 5:
            return taux, nb, 'site + catégorie'

    # Niveau 3 : catégorie uniquement
    if categorie:
        mm = df_merge['categorie'] == categorie
        mu = df_unmatched['categorie'] == categorie
        taux, nb = _taux(mm, mu)
        if nb >= 5:
            return taux, nb, 'catégorie'

    return None, 0, 'aucune donnée'


def get_liste_sites():
    _, _, df = load_data()
    if 'site' in df.columns:
        return sorted(df['site'].dropna().unique().tolist())
    return []


def get_libelle_pour_operation(n_rame, categorie, code_op=None):
    load_data()
    frames = []
    for key in ('df_merge', 'df_prog_unmatched'):
        df = _cache.get(key)
        if df is not None and 'libelle_operation' in df.columns:
            frames.append(df)
    if not frames:
        return None
    combined = pd.concat(frames, ignore_index=True)
    mask = combined['n__rame'].astype(str) == str(n_rame)
    if code_op:
        mask &= combined['code_op'].astype(str).str.upper() == str(code_op).upper()
    sub = combined[mask]['libelle_operation'].dropna()
    return sub.mode().iloc[0] if len(sub) > 0 else None


def get_liste_operations(n_rame=None):
    _, _, df = load_data()
    if n_rame:
        return sorted(df[df['n__rame'] == str(n_rame)]['code_op'].unique().tolist())
    return sorted(df['code_op'].unique().tolist())
