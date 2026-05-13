import streamlit as st
import pandas as pd
import os
import json
import base64
import hashlib
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date

st.set_page_config(layout="wide", page_title="SLA Dashboard", page_icon="📦", initial_sidebar_state="expanded")

# ---------- CSS ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus Jakarta Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding: 1rem 1.5rem !important; max-width: 100% !important; }

[data-testid="stSidebar"] {
    background-color: #1a2235 !important;
    min-width: 220px !important; max-width: 220px !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div { color: #8fa3c0; }
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    color: #8fa3c0 !important; font-size: 13px; font-weight: 500;
    padding: 8px 12px; border-radius: 8px; display: block; margin-bottom: 2px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { color: white !important; background: rgba(255,255,255,0.06); }
[data-testid="stSidebarCollapseButton"] { display: flex !important; visibility: visible !important; }
[data-testid="stSidebar"][aria-expanded="false"] { min-width: 0 !important; width: 0 !important; }
button[data-testid="collapsedControl"] {
    display: flex !important; visibility: visible !important; position: fixed !important;
    left: 0 !important; top: 50% !important; z-index: 999 !important;
    background: #1a2235 !important; border-radius: 0 8px 8px 0 !important;
    border: 1px solid #2a3550 !important; border-left: none !important; padding: 12px 6px !important;
}

.kpi-card {
    background: white; border-radius: 14px; padding: 20px 24px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.07); border: 1px solid #f0f2f5;
}
.kpi-label { font-size: 10px; font-weight: 700; color: #8fa3c0; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.kpi-value { font-size: 32px; font-weight: 800; color: #1a2235; line-height: 1; }
.kpi-sub { font-size: 11px; color: #8fa3c0; margin-top: 6px; }
.section-header { font-size: 13px; font-weight: 700; color: #1a2235; text-transform: uppercase; letter-spacing: 0.08em; margin: 16px 0 2px; }
.section-sub { font-size: 11px; color: #8fa3c0; margin-bottom: 12px; }
.snap-ok { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 10px 16px; font-size: 12px; color: #166534; margin-top: 12px; }
.snap-warn { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px; padding: 10px 16px; font-size: 12px; color: #9a3412; margin-top: 12px; }
hr.divider { border: none; border-top: 1px solid #f0f2f5; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# ---------- PASSWORD ----------
PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "1234"))

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if not st.session_state.password_correct:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown("### 🔐 SLA Dashboard")
            pw = st.text_input("Κωδικός", type="password")
            if pw == PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            elif pw:
                st.error("Λάθος κωδικός")
        st.stop()

check_password()

# ---------- GITHUB ----------
GH        = st.secrets.get("github", {})
GH_TOKEN  = GH.get("token", "")
GH_REPO   = GH.get("repo", "")
GH_BRANCH = GH.get("branch", "main")
GH_RAW    = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}"
GH_HDR    = {"Authorization": f"token {GH_TOKEN}", "Accept": "application/vnd.github.v3+json"}

def gh_get(path):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}?ref={GH_BRANCH}"
    r = requests.get(url, headers=GH_HDR, timeout=10)
    if r.status_code == 200:
        d = r.json()
        return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]
    return None, None

def gh_put(path, content_str, message, sha=None):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    payload = {"message": message, "content": base64.b64encode(content_str.encode()).decode(), "branch": GH_BRANCH}
    if sha: payload["sha"] = sha
    r = requests.put(url, headers=GH_HDR, json=payload, timeout=15)
    return r.status_code in (200, 201)

# ---------- GOOGLE SHEETS ----------
def get_gsheet():
    import gspread
    from google.oauth2.service_account import Credentials
    gs = st.secrets.get("gsheets", {})
    creds_dict = {
        "type": "service_account",
        "project_id":    gs.get("project_id"),
        "private_key_id": gs.get("private_key_id"),
        "private_key":   gs.get("private_key"),
        "client_email":  gs.get("client_email"),
        "client_id":     gs.get("client_id"),
        "token_uri":     gs.get("token_uri", "https://oauth2.googleapis.com/token"),
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "universe_domain": "googleapis.com",
    }
    creds  = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    return client.open_by_key(gs.get("spreadsheet_id", "")).sheet1

def gsheet_backoff(func, *args, **kwargs):
    import time
    for attempt in range(5):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                time.sleep(2 ** attempt)
            else:
                raise
    return func(*args, **kwargs)

@st.cache_data(ttl=60)
def load_master_table():
    try:
        ws   = get_gsheet()
        data = ws.get_all_records(default_blank="")
        if not data:
            return pd.DataFrame(), None
        df = pd.DataFrame(data, dtype=str).replace({"nan": "", "NaT": "", "None": ""})
        return df, None
    except Exception as e:
        # Raise instead of returning empty — prevents accidental data loss
        raise RuntimeError(f"Αποτυχία ανάγνωσης Google Sheet: {e}")

# ---------- HELPERS ----------
@st.cache_data(ttl=3600)
def load_sla_master():
    """Load TK+Πόλη → Ζώνη → SLA days mapping."""
    return pd.read_csv(f"{GH_RAW}/master.csv", dtype=str)

@st.cache_data(ttl=3600)
def load_holidays():
    hol_df = pd.read_csv(f"{GH_RAW}/holidays.csv")
    return set(pd.to_datetime(hol_df["date"], dayfirst=True).dt.date)

def clean_pc(x):
    if pd.isna(x): return ""
    return "".join(filter(str.isdigit, str(x).replace(".0","").replace(" ","").replace("-",""))).strip()

def clean_city(x):
    if pd.isna(x) or str(x).strip() in ("","nan"): return ""
    return str(x).upper().strip()

def normalize_date(d):
    """Normalize to yyyy-mm-dd (unambiguous for Google Sheets)."""
    if not d or str(d).strip() in ("","nan","NaT","None"): return ""
    try:
        return pd.to_datetime(str(d), dayfirst=True, errors="coerce").strftime("%Y-%m-%d")
    except:
        return str(d).strip()

def zone_to_sla(zone):
    """Convert zone name to SLA days."""
    z = str(zone).strip().lower()
    if "in-city" in z or "incity" in z: return 1
    if "remote" in z: return 2
    if "unapproachable" in z: return 3
    return None

def do_sla_matching_tk(df, master_sla):
    """Match TK + Πόλη → SLA days."""
    master_sla = master_sla.copy()
    master_sla["TK_CLEAN"]   = master_sla["Κωδικός"].apply(clean_pc)
    master_sla["CITY_CLEAN"] = master_sla["Πόλη"].apply(clean_city)
    master_sla["SLA_days"]   = master_sla["Ζώνη"].apply(zone_to_sla)

    df = df.copy().reset_index(drop=True)
    df["TK_CLEAN"]   = df["ΤΚ"].apply(clean_pc)
    df["CITY_CLEAN"] = df["Πόλη"].apply(clean_city)
    df["SLA"]  = None
    df["Zone"] = None

    # Step 1: TK + City exact
    m1 = master_sla.dropna(subset=["SLA_days"]).drop_duplicates(["TK_CLEAN","CITY_CLEAN"])
    merged = df[["TK_CLEAN","CITY_CLEAN"]].merge(
        m1[["TK_CLEAN","CITY_CLEAN","SLA_days","Ζώνη"]], on=["TK_CLEAN","CITY_CLEAN"], how="left")
    s1 = merged["SLA_days"].notna().values
    df.loc[s1, "SLA"]  = merged.loc[s1, "SLA_days"].values
    df.loc[s1, "Zone"] = merged.loc[s1, "Ζώνη"].values

    # Step 2: TK only (if unique zone for that TK)
    um2 = df.index[df["SLA"].isna()]
    if len(um2):
        tk_sla = master_sla.groupby("TK_CLEAN").filter(lambda x: x["SLA_days"].nunique()==1)
        tk_map = tk_sla.drop_duplicates("TK_CLEAN")[["TK_CLEAN","SLA_days","Ζώνη"]]
        m2 = df.loc[um2,["TK_CLEAN"]].merge(tk_map, on="TK_CLEAN", how="left")
        m2.index = um2
        s2 = m2["SLA_days"].notna()
        df.loc[um2[s2], "SLA"]  = m2.loc[s2,"SLA_days"].values
        df.loc[um2[s2], "Zone"] = m2.loc[s2,"Ζώνη"].values

    df["SLA"] = pd.to_numeric(df["SLA"], errors="coerce")
    df.drop(columns=["TK_CLEAN","CITY_CLEAN"], inplace=True, errors="ignore")
    return df

def calc_working_days(dm, dp, holidays):
    if pd.isna(dm) or pd.isna(dp): return ""
    days = pd.date_range(dm, dp)
    wd = len([d for d in days if d.weekday() not in (5,6) and d.date() not in holidays]) - 1
    return str(max(0, wd))

def add_working_days(start, n, holidays):
    """Return the date after adding n working days (Mon-Fri, excl. holidays) to start."""
    if pd.isna(start) or pd.isna(n): return pd.NaT
    current = pd.Timestamp(start)
    remaining = int(n)
    while remaining > 0:
        current += pd.Timedelta(days=1)
        if current.weekday() not in (5, 6) and current.date() not in holidays:
            remaining -= 1
    return current

# ---------- MASTER TABLE SCHEMA ----------
MT_COLS = ["Αριθμός","Ημ_Pickup","Ημ_Παράδοσης","Ημ_Επιστροφής",
           "ΤΚ","Πόλη","Κωδ_Καταστήματος","Κατάστημα",
           "Κωδ_Πελάτη","Πελάτης","Κωδ_Συμφωνίας","Συμφωνία",
           "SLA","Zone","Working_Days","Απαράδοτο"]

def update_master_table(df_new):
    """Update Google Sheet with new/updated shipments."""
    load_master_table.clear()  # always read fresh from Sheet
    existing, sha = load_master_table()
    master_sla = load_sla_master()
    holidays   = load_holidays()

    df_new = df_new.copy()

    # Exclude: Ονομασία Παράδοσης == Ονομασία Πελάτη (internal/return)
    if "Ονομασία Παράδοσης" in df_new.columns and "Ονομασία Πελάτη" in df_new.columns:
        df_new = df_new[df_new["Ονομασία Παράδοσης"].astype(str).str.strip() !=
                        df_new["Ονομασία Πελάτη"].astype(str).str.strip()].copy()

    df_new["Αριθμός"] = df_new["Αριθμός"].astype(str)
    df_new["_del_str"] = df_new["Ημ/νία Παράδοσης"].astype(str).replace("NaT","")
    df_new["_ret_str"] = df_new.get("Ημ/νία Επιστροφής Απαραδότου", pd.Series("", index=df_new.index)).astype(str).replace("NaT","")

    if existing.empty:
        # Sheet is empty — do nothing, wait for data to be populated manually
        return pd.DataFrame(), 0, 0, False, sha

    existing["Αριθμός"] = existing["Αριθμός"].astype(str)
    existing_idx = existing.set_index("Αριθμός")

    rows_to_add  = []
    rows_updated = []  # (ar, new_del, new_ret)

    for _, row in df_new.iterrows():
        ar      = str(row["Αριθμός"])
        new_del = normalize_date(str(row["_del_str"]).strip())
        new_ret = normalize_date(str(row["_ret_str"]).strip())
        is_apd  = "1" if new_ret else ""

        if ar not in existing_idx.index:
            rows_to_add.append({
                "Αριθμός":        ar,
                "Ημ_Pickup": normalize_date(str(row["Ημ/νία Pickup"])),
                "Ημ_Παράδοσης":   new_del,
                "Ημ_Επιστροφής":  new_ret,
                "ΤΚ":             clean_pc(row.get("Τ.Κ Παράδοσης","")),
                "Πόλη":           clean_city(row.get("Πόλη Παράδοσης","")),
                "Κωδ_Καταστήματος": str(row.get("Κωδ. Καταστήματος Παράδοσης","")),
                "Κατάστημα":      str(row.get("Κατάστημα Παραλαβής","")),
                "Κωδ_Πελάτη":    str(row.get("Κωδ. Πελάτη","")),
                "Πελάτης":        str(row.get("Ονομασία Πελάτη","")),
                "Κωδ_Συμφωνίας": str(row.get("Κωδ. Συμφωνίας","")),
                "Συμφωνία":       str(row.get("Περιγραφή Συμφωνίας","")),
                "SLA":            "",
                "Zone":           "",
                "Working_Days":   "",
                "Απαράδοτο":      is_apd,
            })
        else:
            existing_del = str(existing_idx.loc[ar, "Ημ_Παράδοσης"]).strip()
            existing_ret = str(existing_idx.loc[ar, "Ημ_Επιστροφής"]).strip() if "Ημ_Επιστροφής" in existing_idx.columns else ""
            if not existing_del and new_del:
                rows_updated.append((ar, new_del, new_ret, is_apd))
            elif not existing_ret and new_ret:
                rows_updated.append((ar, existing_del, new_ret, is_apd))

    n_new     = len(rows_to_add)
    n_updated = len(rows_updated)
    changed   = n_new > 0 or n_updated > 0

    if not changed:
        return existing, 0, 0, False, sha

    ws = get_gsheet()

    # ── 1. SLA matching + WD for new rows ──
    if rows_to_add:
        new_df = pd.DataFrame(rows_to_add)
        new_df = do_sla_matching_tk(new_df, master_sla)
        # Working days for delivered
        new_df["_dm"] = pd.to_datetime(new_df["Ημ_Pickup"], errors="coerce")
        new_df["_dp"] = pd.to_datetime(new_df["Ημ_Παράδοσης"],   errors="coerce")
        new_df["Working_Days"] = new_df.apply(lambda r: calc_working_days(r["_dm"],r["_dp"],holidays), axis=1)
        new_df["SLA"] = new_df["SLA"].astype(str).replace("nan","")
        new_df.drop(columns=["_dm","_dp"], inplace=True, errors="ignore")
        new_rows = new_df[MT_COLS].fillna("").astype(str).values.tolist()
        for i in range(0, len(new_rows), 500):
            gsheet_backoff(ws.append_rows, new_rows[i:i+500], value_input_option="RAW")

    # ── 2. Batch update pending→delivered ──
    if rows_updated:
        all_data = gsheet_backoff(ws.get_all_values)
        ar_to_row = {str(r[0]): i+1 for i, r in enumerate(all_data) if i > 0}
        headers = all_data[0]

        def col_idx(name):
            try: return headers.index(name) + 1
            except: return None

        col_del = col_idx("Ημ_Παράδοσης")
        col_ret = col_idx("Ημ_Επιστροφής")
        col_wd  = col_idx("Working_Days")
        col_apd = col_idx("Απαράδοτο")
        col_dm  = col_idx("Ημ_Pickup")

        import gspread.utils as gu
        batch = []
        for ar, new_del, new_ret, is_apd in rows_updated:
            if ar not in ar_to_row: continue
            rn = ar_to_row[ar]
            dm_str = all_data[rn-1][col_dm-1] if col_dm else ""
            dm = pd.to_datetime(dm_str, errors="coerce")
            dp = pd.to_datetime(new_del, errors="coerce")
            wd = calc_working_days(dm, dp, holidays)

            if col_del: batch.append({"range": f"{gu.rowcol_to_a1(rn,col_del)}", "values": [[new_del]]})
            if col_ret: batch.append({"range": f"{gu.rowcol_to_a1(rn,col_ret)}", "values": [[new_ret]]})
            if col_wd:  batch.append({"range": f"{gu.rowcol_to_a1(rn,col_wd)}",  "values": [[wd]]})
            if col_apd: batch.append({"range": f"{gu.rowcol_to_a1(rn,col_apd)}", "values": [[is_apd]]})

        if batch:
            gsheet_backoff(ws.batch_update, batch)

    load_master_table.clear()
    return existing, n_new, n_updated, changed, sha

# ---------- LOAD & PROCESS ----------
@st.cache_data(ttl=120)
def load_and_process():
    master_sla = load_sla_master()
    holidays   = load_holidays()
    mt, _      = load_master_table()

    if mt is None or len(mt) == 0 or "Ημ_Pickup" not in mt.columns:
        st.error(f"Sheet empty or missing columns. mt={mt is not None}, len={len(mt) if mt is not None else 0}, cols={list(mt.columns) if mt is not None and len(mt)>0 else []}")
        return pd.DataFrame()

    # Normal path: from Google Sheet
    col_map = {
        "Ημ_Pickup": "Ημ/νία Pickup",
        "Ημ_Παράδοσης":   "Ημ/νία Παράδοσης",
        "Ημ_Επιστροφής":  "Ημ/νία Επιστροφής",
        "Κωδ_Καταστήματος": "Κωδ. Καταστήματος Παράδοσης",
    }
    df = mt.rename(columns={k:v for k,v in col_map.items() if k in mt.columns})
    df["Κατάστημα"] = df.get("Κωδ. Καταστήματος Παράδοσης","").astype(str).str.strip() + " " + df.get("Κατάστημα","").astype(str).str.strip()

    # Dates — ISO format (yyyy-mm-dd) from Sheet, no dayfirst
    df["Ημ/νία Pickup"]      = pd.to_datetime(df["Ημ/νία Pickup"],    errors="coerce")
    df["Ημ/νία Παράδοσης"]   = pd.to_datetime(df["Ημ/νία Παράδοσης"].astype(str).str.strip().replace({"":"NaT","nan":"NaT"}), errors="coerce")
    df["Ημ/νία Επιστροφής"]  = pd.to_datetime(df.get("Ημ/νία Επιστροφής","").astype(str).str.strip().replace({"":"NaT","nan":"NaT"}), errors="coerce")

    # SLA for rows missing it
    needs_sla = df["SLA"].isna() | df["SLA"].astype(str).str.strip().isin(["","nan"])
    if needs_sla.sum() > 0:
        df_to_match = df[needs_sla].copy().reset_index(drop=True)
        df_to_match["orig_idx"] = df[needs_sla].index.tolist()
        matched = do_sla_matching_tk(df_to_match, master_sla)
        for i, orig_i in enumerate(df_to_match["orig_idx"]):
            df.at[orig_i, "SLA"]  = str(matched.at[i,"SLA"]) if pd.notna(matched.at[i,"SLA"]) else ""
            df.at[orig_i, "Zone"] = str(matched.at[i,"Zone"]) if "Zone" in matched.columns and pd.notna(matched.at[i,"Zone"]) else ""

    df["SLA"]         = pd.to_numeric(df["SLA"], errors="coerce")
    df["working_days"]= pd.to_numeric(df["Working_Days"], errors="coerce")
    df["Απαράδοτο"]   = df.get("Απαράδοτο","").astype(str).str.strip().isin(["1","True","TRUE","true"])

    # Debug
    st.session_state["_debug_del"] = f"Παράδοση notna: {df['Ημ/νία Παράδοσης'].notna().sum()} / {len(df)} | sample: {df['Ημ/νία Παράδοσης'].dropna().head(3).tolist()}"

    return df

# ---------- METRICS ----------
def metrics(df, holidays=None):
    today = pd.Timestamp(date.today())

    # Delivered: have Ημ/νία Παράδοσης
    delivered = df[df["Ημ/νία Παράδοσης"].notna()].copy()
    if len(delivered):
        delivered["on_time"]    = delivered["working_days"] <= delivered["SLA"]
        delivered["delay_days"] = (delivered["working_days"] - delivered["SLA"]).clip(lower=0)

    # Not delivered: no Ημ/νία Παράδοσης
    not_del = df[df["Ημ/νία Παράδοσης"].isna()].copy()

    if holidays is not None and len(not_del):
        not_del["_expected"] = not_del.apply(
            lambda r: add_working_days(r["Ημ/νία Pickup"], r["SLA"], holidays)
            if pd.notna(r.get("SLA")) else pd.NaT, axis=1
        )
        pending = not_del[not_del["_expected"].isna() | (not_del["_expected"] >= today)].copy()
        apd     = not_del[not_del["_expected"].notna() & (not_del["_expected"] < today)].copy()
    else:
        pending = not_del.copy()
        apd     = pd.DataFrame(columns=df.columns)

    return delivered, apd, pending

# ════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════
with st.sidebar:
    st.markdown(f"""
    <div style='padding:16px 12px 8px;'>
        <div style='font-size:18px;font-weight:800;color:white;'>📦 SLA Dashboard</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<div style='font-size:10px;color:#5a7090;text-transform:uppercase;letter-spacing:0.08em;padding:0 12px 4px;'>Πλοήγηση</div>", unsafe_allow_html=True)
    page = st.radio("Πλοήγηση", [
        "🏠  Επισκόπηση",
        "🗺️  Ανάλυση Νομού",
        "🏪  Ανάλυση Καταστήματος",
    ], label_visibility="collapsed")

# ---------- LOAD DATA ----------
with st.spinner("Φόρτωση δεδομένων..."):
    df_full = load_and_process()

# Temporary debug

if df_full is None or len(df_full) == 0:
    st.error("Δεν βρέθηκαν δεδομένα.")
    st.stop()

# ---------- CLIENT/AGREEMENT FILTERS (always visible) ----------
min_d = df_full["Ημ/νία Pickup"].min().date()
max_d = df_full["Ημ/νία Pickup"].max().date()

# Build client list with name (code - name)
client_options = {"Όλοι": "Όλοι"}
for _, row in df_full.drop_duplicates("Κωδ_Πελάτη").iterrows():
    code = str(row.get("Κωδ_Πελάτη","")).strip()
    name = str(row.get("Πελάτης","")).strip()
    if code and code != "nan":
        label = f"{name}" if name and name != "nan" else code
        client_options[code] = label

ff1, ff2 = st.columns([3, 3])
with ff1:
    client_label = st.selectbox("Πελάτης", list(client_options.values()), key="client")
    client_filter = [k for k,v in client_options.items() if v == client_label][0]

# Build agreement list
if client_filter != "Όλοι":
    sub_df = df_full[df_full["Κωδ_Πελάτη"] == client_filter]
else:
    sub_df = df_full

agree_options = {"Όλες": "Όλες"}
for _, row in sub_df.drop_duplicates("Κωδ_Συμφωνίας").iterrows():
    code = str(row.get("Κωδ_Συμφωνίας","")).strip()
    name = str(row.get("Συμφωνία","")).strip()
    if code and code != "nan":
        label = f"{name}" if name and name != "nan" else code
        agree_options[code] = label

with ff2:
    agree_label  = st.selectbox("Συμφωνία", list(agree_options.values()), key="agree")
    agree_filter = [k for k,v in agree_options.items() if v == agree_label][0]

# Apply client/agreement filter
df_filtered = df_full.copy()
if client_filter != "Όλοι":
    df_filtered = df_filtered[df_filtered["Κωδ_Πελάτη"] == client_filter]
if agree_filter != "Όλες":
    df_filtered = df_filtered[df_filtered["Κωδ_Συμφωνίας"] == agree_filter]

# ════════════════════════════════════
# PAGE: ΕΠΙΣΚΟΠΗΣΗ
# ════════════════════════════════════
if "Επισκόπηση" in page:
    min_d2 = df_filtered["Ημ/νία Pickup"].min().date() if len(df_filtered) else min_d
    max_d2 = df_filtered["Ημ/νία Pickup"].max().date() if len(df_filtered) else max_d

    fc1, fc2 = st.columns([2, 2])
    with fc1: date_from = st.date_input("Από", value=min_d2, min_value=min_d2, max_value=max_d2, key="ep_df")
    with fc2: date_to   = st.date_input("Έως", value=max_d2, min_value=min_d2, max_value=max_d2, key="ep_dt")

    df = df_filtered[
        (df_filtered["Ημ/νία Pickup"].dt.date >= date_from) &
        (df_filtered["Ημ/νία Pickup"].dt.date <= date_to)
    ].copy()

    delivered, apd, pending = metrics(df, holidays=load_holidays())

    total     = len(df)
    n_del     = len(delivered)
    n_apd     = len(apd)
    n_pend    = len(pending)
    n_ontime  = int(delivered["on_time"].sum()) if len(delivered) else 0
    sla_pct   = n_ontime / n_del * 100 if n_del else 0
    apd_pct   = n_apd / total * 100 if total else 0

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # KPIs
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    kpis = [
        (k1, "📦", "ΣΥΝΟΛΟ ΑΠΟΣΤΟΛΩΝ", f"{total:,}", "100%"),
        (k2, "✅", "ΠΑΡΑΔΟΘΗΚΑΝ",      f"{n_del:,}", f"{n_del/total*100:.2f}% του συνόλου" if total else ""),
        (k3, "🎯", "ΕΝΤΟΣ SLA",         f"{n_ontime:,}", f"{sla_pct:.2f}% παραδοθέντων"),
        (k4, "📊", "SLA % (ΕΝΤΟΣ)",     f"{sla_pct:.2f}%", f"{n_ontime:,} / {n_del:,}"),
        (k5, "⏳", "PENDING SLA",        f"{n_pend:,}", f"{n_pend/total*100:.2f}% του συνόλου" if total else ""),
        (k6, "⚠️", "ΑΠΑΡΑΔΟΤΑ",         f"{n_apd:,}", f"{apd_pct:.2f}% του συνόλου"),
    ]
    for col, icon, label, val, sub in kpis:
        with col:
            color = "#7c3aed" if "SLA%" in label else "#1a2235"
            st.markdown(f"""<div class="kpi-card">
                <div style="font-size:24px;margin-bottom:4px;">{icon}</div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value" style="color:{color};">{val}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # SLA Zone analysis (donuts)
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΖΩΝΗ ΠΑΡΑΔΟΣΗΣ</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-sub">(ΟΛΟ ΤΟ ΔΙΑΣΤΗΜΑ)</div>', unsafe_allow_html=True)

    zone_map = {1: "24H (1 ΕΡΓΑΣΙΜΗ)", 2: "48H (2 ΕΡΓΑΣΙΜΕΣ)", 3: "72H (3 ΕΡΓΑΣΙΜΕΣ)"}

    def donut_svg(pct, c_in, c_out, size=200):
        r=72; cx=cy=90; stroke=18; circ=2*3.14159*r
        filled=circ*pct/100; gap=circ-filled
        return f"""<svg viewBox="0 0 180 180" width="{size}" height="{size}" style="flex-shrink:0;">
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c_out}" stroke-width="{stroke}"/>
            <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c_in}" stroke-width="{stroke}"
                stroke-dasharray="{filled:.2f} {gap:.2f}" stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>
            <text x="{cx}" y="{cy-8}" text-anchor="middle" dominant-baseline="central"
                font-family="Plus Jakarta Sans,sans-serif" font-size="26" font-weight="800" fill="#1a2235">{pct:.1f}%</text>
            <text x="{cx}" y="{cy+18}" text-anchor="middle"
                font-family="Plus Jakarta Sans,sans-serif" font-size="11" font-weight="600" fill="#8fa3c0">εντός SLA</text>
        </svg>"""

    zone_cols = st.columns(3)
    for i, (sla_d, lbl) in enumerate(zone_map.items()):
        g = delivered[delivered["SLA"]==sla_d] if len(delivered) else pd.DataFrame()
        with zone_cols[i]:
            if not len(g):
                st.markdown(f'<div style="background:white;border-radius:14px;padding:16px;box-shadow:0 1px 8px rgba(0,0,0,0.07);text-align:center;color:#ccc;">{lbl}<br>Δεν υπάρχουν δεδομένα</div>', unsafe_allow_html=True)
                continue
            ot=int(g["on_time"].sum()); lat=len(g)-ot; pct=ot/len(g)*100
            st.markdown(f"""<div style="background:white;border-radius:14px;padding:16px 20px;box-shadow:0 1px 8px rgba(0,0,0,0.07);border:1px solid #f0f2f5;display:flex;align-items:center;gap:20px;">
                {donut_svg(pct,"#22c55e","#fee2e2")}
                <div style="flex:1;">
                    <div style="font-size:11px;font-weight:700;color:#8fa3c0;text-transform:uppercase;margin-bottom:14px;">{lbl}</div>
                    <div style="font-size:13px;margin-bottom:6px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#22c55e;margin-right:7px;"></span>Εντός <b>{ot:,}</b> <span style="color:#8fa3c0">({pct:.2f}%)</span></div>
                    <div style="font-size:13px;margin-bottom:14px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444;margin-right:7px;"></span>Εκτός <b>{lat:,}</b> <span style="color:#8fa3c0">({100-pct:.2f}%)</span></div>
                    <div style="font-size:11px;color:#8fa3c0;">Σύνολο παραδοθέντων</div>
                    <div style="font-size:18px;font-weight:800;color:#1a2235;">{len(g):,}</div>
                </div>
            </div>""", unsafe_allow_html=True)


    # Delay analysis
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">ΚΑΘΥΣΤΕΡΗΣΗ ΠΑΡΑΔΟΣΕΩΝ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">(ΟΛΟ ΤΟ ΔΙΑΣΤΗΜΑ)</div>', unsafe_allow_html=True)

    late = delivered[~delivered["on_time"]].copy() if len(delivered) else pd.DataFrame()

    def delay_donut_svg(count, z1, z2, z3, size=160):
        """3-segment donut: z1=24h(green), z2=48h(orange), z3=72h(red)"""
        r=62; cx=cy=78; stroke=16; circ=2*3.14159*r
        total = z1+z2+z3 if (z1+z2+z3)>0 else 1
        # segments proportional to zone counts
        s1=circ*z1/total; s2=circ*z2/total; s3=circ*z3/total
        # build arcs: start at -90deg, segments in order 24h->48h->72h
        def arc(cx,cy,r,stroke,color,dashlen,offset_deg):
            gap=circ-dashlen
            return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-dasharray="{dashlen:.2f} {gap:.2f}" stroke-linecap="butt" transform="rotate({offset_deg} {cx} {cy})"/>'
        # cumulative offsets in degrees
        deg1 = -90
        deg2 = deg1 + 360*z1/total
        deg3 = deg2 + 360*z2/total
        svg = f'<svg viewBox="0 0 156 156" width="{size}" height="{size}" style="flex-shrink:0;">'
        svg += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#f1f5f9" stroke-width="{stroke}"/>'
        if z1>0: svg += arc(cx,cy,r,stroke,"#22c55e",s1,deg1)
        if z2>0: svg += arc(cx,cy,r,stroke,"#f97316",s2,deg2)
        if z3>0: svg += arc(cx,cy,r,stroke,"#ef4444",s3,deg3)
        svg += f'<text x="{cx}" y="{cy-6}" text-anchor="middle" dominant-baseline="central" font-family="Plus Jakarta Sans,sans-serif" font-size="22" font-weight="800" fill="#1a2235">{count:,}</text>'
        svg += f'<text x="{cx}" y="{cy+16}" text-anchor="middle" font-family="Plus Jakarta Sans,sans-serif" font-size="10" font-weight="600" fill="#8fa3c0">αποστολές</text>'
        svg += '</svg>'
        return svg

    delay_cols = st.columns(3)
    delay_bands = [
        (1, 2,  "1 ΗΜΕΡΑ ΚΑΘΥΣΤΕΡΗΣΗ",   "#f97316"),
        (2, 3,  "2 ΗΜΕΡΕΣ ΚΑΘΥΣΤΕΡΗΣΗ",  "#ef4444"),
        (3, 999,"3+ ΗΜΕΡΕΣ ΚΑΘΥΣΤΕΡΗΣΗ", "#7c3aed"),
    ]
    n_late = len(late)
    for i, (d_min, d_max, lbl, color) in enumerate(delay_bands):
        with delay_cols[i]:
            if not n_late:
                st.markdown(f'<div style="background:white;border-radius:14px;padding:16px;box-shadow:0 1px 8px rgba(0,0,0,0.07);text-align:center;color:#ccc;">{lbl}<br>Δεν υπάρχουν δεδομένα</div>', unsafe_allow_html=True)
                continue
            grp = late[(late["delay_days"] >= d_min) & (late["delay_days"] < d_max)]
            cnt = len(grp)
            pct = cnt / n_late * 100 if n_late else 0
            # breakdown by zone (24h=1, 48h=2, 72h=3)
            z1 = len(grp[grp["SLA"]==1]); z2 = len(grp[grp["SLA"]==2]); z3 = len(grp[grp["SLA"]==3])
            pct_of_del = cnt / n_del * 100 if n_del else 0
            st.markdown(f"""<div style="background:white;border-radius:14px;padding:16px 20px;box-shadow:0 1px 8px rgba(0,0,0,0.07);border:1px solid #f0f2f5;display:flex;align-items:center;gap:16px;">
                {delay_donut_svg(cnt, z1, z2, z3)}
                <div style="flex:1;">
                    <div style="font-size:11px;font-weight:700;color:#8fa3c0;text-transform:uppercase;margin-bottom:12px;">{lbl}</div>
                    <div style="font-size:12px;margin-bottom:4px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px;"></span>24h <b>{z1:,}</b> <span style="color:#8fa3c0">({z1/cnt*100:.1f}%)</span></div>
                    <div style="font-size:12px;margin-bottom:4px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f97316;margin-right:6px;"></span>48h <b>{z2:,}</b> <span style="color:#8fa3c0">({z2/cnt*100:.1f}%)</span></div>
                    <div style="font-size:12px;margin-bottom:12px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#ef4444;margin-right:6px;"></span>72h <b>{z3:,}</b> <span style="color:#8fa3c0">({z3/cnt*100:.1f}%)</span></div>
                    <div style="font-size:11px;color:#8fa3c0;">% επί παραδοθέντων</div>
                    <div style="font-size:16px;font-weight:800;color:#1a2235;">{pct_of_del:.1f}%</div>
                </div>
            </div>""", unsafe_allow_html=True)

    # Monthly performance
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">ΜΗΝΙΑΙΑ ΕΠΙΔΟΣΗ</div>', unsafe_allow_html=True)

    if len(delivered):
        import calendar
        MONTH_GR = ["","ΙΑΝΟΥΑΡΙΟΣ","ΦΕΒΡΟΥΑΡΙΟΣ","ΜΑΡΤΙΟΣ","ΑΠΡΙΛΙΟΣ","ΜΑΪΟΣ","ΙΟΥΝΙΟΣ",
                    "ΙΟΥΛΙΟΣ","ΑΥΓΟΥΣΤΟΣ","ΣΕΠΤΕΜΒΡΙΟΣ","ΟΚΤΩΒΡΙΟΣ","ΝΟΕΜΒΡΙΟΣ","ΔΕΚΕΜΒΡΙΟΣ"]
        today = date.today()
        months = []
        for delta in range(2, -1, -1):
            m = today.month - delta
            y = today.year
            while m <= 0: m += 12; y -= 1
            is_cur = (y == today.year and m == today.month)
            months.append((y, m, is_cur))
        mo_cols = st.columns(3)
        for col_i, (yr, mo, is_current) in enumerate(months):
            mask = (delivered["Ημ/νία Pickup"].dt.year == yr) & (delivered["Ημ/νία Pickup"].dt.month == mo)
            sub = delivered[mask]
            with mo_cols[col_i]:
                lbl = f"{MONTH_GR[mo]} {yr}"
                if is_current:
                    lbl += f" (ΕΩΣ {today.strftime('%d/%m')})"
                if not len(sub):
                    st.markdown(f'<div style="background:white;border-radius:14px;padding:20px;box-shadow:0 1px 8px rgba(0,0,0,0.07);"><div style="font-size:11px;font-weight:700;color:#8fa3c0;">{lbl}</div><div style="color:#ccc;margin-top:8px;">Δεν υπάρχουν δεδομένα</div></div>', unsafe_allow_html=True)
                    continue
                total_mo = len(sub)
                ontime_mo = int(sub["on_time"].sum())
                pct_mo = ontime_mo / total_mo * 100 if total_mo else 0
                pct_color = "#22c55e" if pct_mo>=90 else "#f97316" if pct_mo>=75 else "#ef4444"
                zone_rows = ""
                for sla_d, zlbl in [(1,"24h (1 εργάσιμη)"),(2,"48h (2 εργάσιμες)"),(3,"72h (3 εργάσιμες)")]:
                    zg = sub[sub["SLA"]==sla_d]
                    if not len(zg): continue
                    zpct = int(zg["on_time"].sum()) / len(zg) * 100
                    zcolor = "#22c55e" if zpct>=90 else "#f97316" if zpct>=75 else "#ef4444"
                    bar_w = max(0, min(100, zpct))
                    zone_rows += (
                        '<div style="margin-bottom:10px;">'
                        '<div style="display:flex;justify-content:space-between;font-size:11px;color:#8fa3c0;margin-bottom:3px;">'
                        f'<span>{zlbl}</span><span style="font-weight:700;color:{zcolor};">{zpct:.2f}%</span>'
                        '</div>'
                        '<div style="background:#f1f5f9;border-radius:4px;height:6px;">'
                        f'<div style="background:{zcolor};width:{bar_w:.1f}%;height:6px;border-radius:4px;"></div>'
                        '</div></div>'
                    )
                st.markdown(
                    f'<div style="background:white;border-radius:14px;padding:20px 24px;box-shadow:0 1px 8px rgba(0,0,0,0.07);border:1px solid #f0f2f5;">'
                    f'<div style="font-size:11px;font-weight:700;color:#8fa3c0;text-transform:uppercase;margin-bottom:6px;">{lbl}</div>'
                    f'<div style="font-size:10px;color:#8fa3c0;margin-bottom:4px;">SLA % (ΕΝΤΟΣ)</div>'
                    f'<div style="font-size:30px;font-weight:800;color:{pct_color};margin-bottom:2px;">{pct_mo:.2f}%</div>'
                    f'<div style="font-size:11px;color:#8fa3c0;margin-bottom:16px;">{ontime_mo:,} / {total_mo:,}</div>'
                    f'{zone_rows}'
                    f'</div>',
                    unsafe_allow_html=True
                )

    # Update master table
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    if GH_TOKEN and GH_REPO:
        with st.spinner("🔄 Έλεγχος αλλαγών..."):
            try:
                df_new_data = pd.read_csv(f"{GH_RAW}/data.csv")
            except:
                df_new_data = None
            if df_new_data is not None:
                try:
                    existing_before, _ = load_master_table()
                    n_existing = len(existing_before) if existing_before is not None else 0
                    _, n_new, n_updated, changed, _ = update_master_table(df_new_data)
                    existing_after, _ = load_master_table()
                    n_after = len(existing_after) if existing_after is not None else 0
                    st.markdown(f'<div class="snap-warn">🔍 DEBUG: Sheet πριν={n_existing} | data.csv={len(df_new_data)} | νέες={n_new} | updated={n_updated} | Sheet μετά={n_after}</div>', unsafe_allow_html=True)
                    if changed:
                        load_and_process.clear()
                        msg = f"✅ Νέο snapshot: <b>{n_new}</b> νέες αποστολές, <b>{n_updated}</b> pending → delivered"
                        st.markdown(f'<div class="snap-ok">{msg}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="snap-ok">✅ Καμία αλλαγή — δεν χρειάζεται νέο snapshot</div>', unsafe_allow_html=True)
                except RuntimeError as e:
                    st.markdown(f'<div class="snap-warn">⚠️ {e}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="snap-warn">⚠️ GitHub token δεν έχει οριστεί</div>', unsafe_allow_html=True)

# ════════════════════════════════════
# PAGE: ΑΝΑΛΥΣΗ ΝΟΜΟΥ
# ════════════════════════════════════
elif "Νομού" in page:
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΝΟΜΟ / ΠΕΡΙΟΧΗ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Σύγκριση δύο περιόδων βάσει ημερομηνίας δημιουργίας</div>', unsafe_allow_html=True)

    all_min = df_filtered["Ημ/νία Pickup"].min().date() if len(df_filtered) else min_d
    all_max = df_filtered["Ημ/νία Pickup"].max().date() if len(df_filtered) else max_d

    p1, p2, p3, p4, _ = st.columns([2,2,2,2,1])
    with p1: p1_from = st.date_input("Περίοδος Α — Από", value=all_min, key="p1f")
    with p2: p1_to   = st.date_input("Περίοδος Α — Έως", value=all_max, key="p1t")
    with p3: p2_from = st.date_input("Περίοδος Β — Από", value=all_min, key="p2f")
    with p4: p2_to   = st.date_input("Περίοδος Β — Έως", value=all_max, key="p2t")

    def period_stats(d_from, d_to):
        mask = (df_filtered["Ημ/νία Pickup"].dt.date >= d_from) & (df_filtered["Ημ/νία Pickup"].dt.date <= d_to)
        sub  = df_filtered[mask]
        d, _, _ = metrics(sub, holidays=load_holidays())
        if not len(d) or "Zone" not in d.columns: return pd.DataFrame()
        r = d.groupby("Zone").agg(total=("on_time","count"), on_time=("on_time","sum")).reset_index()
        r["sla_pct"] = (r["on_time"]/r["total"]*100).round(2)
        r.columns = ["Περιοχή","total","on_time","sla_pct"]
        return r

    grp_A = period_stats(p1_from, p1_to)
    grp_B = period_stats(p2_from, p2_to)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    if grp_A.empty:
        st.info("Δεν υπάρχουν δεδομένα για την Περίοδο Α.")
    else:
        if not grp_B.empty:
            merged = grp_A[["Περιοχή","sla_pct","total"]].merge(
                grp_B[["Περιοχή","sla_pct","total"]], on="Περιοχή", how="outer", suffixes=("_A","_B")).fillna(0)
            merged["diff"] = (merged["sla_pct_B"] - merged["sla_pct_A"]).round(2)
            merged["arrow"] = merged["diff"].apply(lambda d: "▲" if d>0.5 else ("▼" if d<-0.5 else "→"))
            merged["arrow_color"] = merged["diff"].apply(lambda d: "#16a34a" if d>0.5 else ("#ef4444" if d<-0.5 else "#8fa3c0"))
            merged["diff_label"] = merged.apply(lambda r: f"{r['arrow']} {abs(r['diff']):.1f}%", axis=1)

            sc1, sc2 = st.columns([3,1])
            with sc2: sort_dir = st.radio("Ταξινόμηση", ["▲","▼"], horizontal=True, key="nsort")
            merged = merged.sort_values("diff", ascending=(sort_dir=="▼"))
            zones = merged["Περιοχή"].tolist()

            fig = go.Figure()
            fig.add_trace(go.Bar(y=zones, x=merged["sla_pct_A"], orientation="h", name="Περίοδος Α",
                marker_color="#7c3aed", opacity=0.45, width=0.35, offset=-0.35))
            fig.add_trace(go.Bar(y=zones, x=merged["sla_pct_B"], orientation="h", name="Περίοδος Β",
                marker_color="#0ea5e9", opacity=0.85, width=0.35, offset=0))
            for _, row in merged.iterrows():
                fig.add_annotation(y=row["Περιοχή"], x=max(row["sla_pct_A"],row["sla_pct_B"])+1,
                    text=f"<b>{row['diff_label']}</b>", showarrow=False,
                    font=dict(size=9, color=row["arrow_color"], family="Plus Jakarta Sans"), xanchor="left")
            fig.update_layout(height=max(400, len(zones)*35), barmode="overlay",
                paper_bgcolor="white", plot_bgcolor="white",
                margin=dict(t=10,b=20,l=20,r=80), font=dict(family="Plus Jakarta Sans"),
                xaxis=dict(range=[50,115], ticksuffix="%", gridcolor="#f0f2f5"),
                yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=1.02), bargap=0.3)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            tbl = merged[["Περιοχή","sla_pct_A","total_A","sla_pct_B","total_B","diff_label"]].copy()
            tbl.columns = ["Περιοχή","SLA% Α","Αποστολές Α","SLA% Β","Αποστολές Β","Μεταβολή"]
            tbl["Αποστολές Α"] = tbl["Αποστολές Α"].astype(int)
            tbl["Αποστολές Β"] = tbl["Αποστολές Β"].astype(int)
            st.dataframe(tbl, use_container_width=True, hide_index=True)

# ════════════════════════════════════
# PAGE: ΑΝΑΛΥΣΗ ΚΑΤΑΣΤΗΜΑΤΟΣ
# ════════════════════════════════════
elif "Καταστήματος" in page:
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΚΑΤΑΣΤΗΜΑ</div>', unsafe_allow_html=True)

    all_min = df_filtered["Ημ/νία Pickup"].min().date() if len(df_filtered) else min_d
    all_max = df_filtered["Ημ/νία Pickup"].max().date() if len(df_filtered) else max_d

    sp1, sp2, sp3, sp4, _ = st.columns([2,2,2,2,1])
    with sp1: s_p1_from = st.date_input("Περίοδος Α — Από", value=all_min, key="sp1f")
    with sp2: s_p1_to   = st.date_input("Περίοδος Α — Έως", value=all_max, key="sp1t")
    with sp3: s_p2_from = st.date_input("Περίοδος Β — Από", value=all_min, key="sp2f")
    with sp4: s_p2_to   = st.date_input("Περίοδος Β — Έως", value=all_max, key="sp2t")

    def shop_stats(d_from, d_to):
        mask = (df_filtered["Ημ/νία Pickup"].dt.date >= d_from) & (df_filtered["Ημ/νία Pickup"].dt.date <= d_to)
        sub  = df_filtered[mask]
        d, _, _ = metrics(sub, holidays=load_holidays())
        if not len(d) or "Κατάστημα" not in d.columns: return pd.DataFrame()
        r = d.groupby("Κατάστημα").agg(total=("on_time","count"), on_time=("on_time","sum")).reset_index()
        r["sla_pct"] = (r["on_time"]/r["total"]*100).round(2)
        r["late"]    = r["total"] - r["on_time"]
        return r

    grp_A = shop_stats(s_p1_from, s_p1_to)
    grp_B = shop_stats(s_p2_from, s_p2_to)

    if grp_A.empty:
        st.info("Δεν υπάρχουν δεδομένα καταστήματος για την περίοδο Α.")
        st.stop()

    period_a_lbl = f"{s_p1_from.strftime('%d/%m/%Y')} – {s_p1_to.strftime('%d/%m/%Y')}"

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    def shop_cards(grp, ascending):
        top = grp.sort_values("sla_pct", ascending=ascending).head(10)
        cols = st.columns(5)
        for i, (_, row) in enumerate(top.iterrows()):
            pct = row["sla_pct"]
            badge = "#22c55e" if pct>=90 else "#f97316" if pct>=75 else "#ef4444"
            with cols[i%5]:
                st.markdown(f"""<div style="background:white;border-radius:12px;padding:14px;box-shadow:0 1px 6px rgba(0,0,0,0.07);
                    border:1px solid #f0f2f5;margin-bottom:10px;border-top:3px solid {badge};">
                    <div style="font-size:10px;color:#8fa3c0;font-weight:600;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                        title="{row['Κατάστημα']}">{row['Κατάστημα']}</div>
                    <div style="font-size:22px;font-weight:800;color:{badge};">{pct:.1f}%</div>
                    <div style="font-size:11px;color:#8fa3c0;">{row['total']:,} αποστολές</div>
                </div>""", unsafe_allow_html=True)

    st.markdown(f'#### 🏆 Top 10 — Καλύτερη επίδοση <span style="font-size:12px;color:#8fa3c0;font-weight:400;">Περίοδος Α: {period_a_lbl}</span>', unsafe_allow_html=True)
    shop_cards(grp_A, False)
    st.markdown(f'#### ⚠️ Bottom 10 — Χαμηλότερη επίδοση <span style="font-size:12px;color:#8fa3c0;font-weight:400;">Περίοδος Α: {period_a_lbl}</span>', unsafe_allow_html=True)
    shop_cards(grp_A, True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    if not grp_B.empty:
        merged_s = grp_A[["Κατάστημα","sla_pct","total"]].merge(
            grp_B[["Κατάστημα","sla_pct","total"]], on="Κατάστημα", how="outer", suffixes=("_A","_B")).fillna(0)
        merged_s["diff"] = (merged_s["sla_pct_B"] - merged_s["sla_pct_A"]).round(2)
        merged_s["arrow"] = merged_s["diff"].apply(lambda d: "▲" if d>0.5 else ("▼" if d<-0.5 else "→"))
        merged_s["arrow_color"] = merged_s["diff"].apply(lambda d: "#16a34a" if d>0.5 else ("#ef4444" if d<-0.5 else "#8fa3c0"))
        merged_s["diff_label"] = merged_s.apply(lambda r: f"{r['arrow']} {abs(r['diff']):.1f}%", axis=1)

        sc1, sc2 = st.columns([3,1])
        with sc2: s_sort = st.radio("Ταξινόμηση", ["▲","▼"], horizontal=True, key="s_sort")
        merged_s = merged_s.sort_values("diff", ascending=(s_sort=="▼"))
        shops_s  = merged_s["Κατάστημα"].tolist()

        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(y=shops_s, x=merged_s["sla_pct_A"], orientation="h", name="Περίοδος Α",
            marker_color="#7c3aed", opacity=0.45, width=0.35, offset=-0.35))
        fig_s.add_trace(go.Bar(y=shops_s, x=merged_s["sla_pct_B"], orientation="h", name="Περίοδος Β",
            marker_color="#0ea5e9", opacity=0.85, width=0.35, offset=0))
        for _, row in merged_s.iterrows():
            fig_s.add_annotation(y=row["Κατάστημα"], x=max(row["sla_pct_A"],row["sla_pct_B"])+1,
                text=f"<b>{row['diff_label']}</b>", showarrow=False,
                font=dict(size=9, color=row["arrow_color"], family="Plus Jakarta Sans"), xanchor="left")
        fig_s.update_layout(height=max(500,len(shops_s)*28), barmode="overlay",
            paper_bgcolor="white", plot_bgcolor="white",
            margin=dict(t=10,b=20,l=20,r=80), font=dict(family="Plus Jakarta Sans"),
            xaxis=dict(range=[50,115], ticksuffix="%", gridcolor="#f0f2f5"),
            yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=1.02), bargap=0.3)
        st.plotly_chart(fig_s, use_container_width=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    tbl_s = grp_A.sort_values("sla_pct")[["Κατάστημα","sla_pct","total","on_time","late"]].copy()
    tbl_s.columns = ["Κατάστημα","SLA%","Σύνολο","Εντός SLA","Εκτός SLA"]
    st.dataframe(tbl_s, use_container_width=True, hide_index=True)
