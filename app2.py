import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
import gspread, json, base64, time, requests
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide", page_title="SLA Dashboard", page_icon="📦", initial_sidebar_state="expanded")

# ---------- CSS ----------
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Plus Jakarta Sans',sans-serif!important}
.block-container{padding:1.5rem 2rem!important}
.kpi-card{background:white;border-radius:14px;padding:18px 20px;box-shadow:0 1px 8px rgba(0,0,0,0.07);border:1px solid #f0f2f5}
.kpi-label{font-size:10px;font-weight:700;color:#8fa3c0;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.kpi-value{font-size:28px;font-weight:800;color:#1a2235}
.kpi-sub{font-size:11px;color:#8fa3c0;margin-top:2px}
.section-header{font-size:13px;font-weight:700;color:#1a2235;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.section-sub{font-size:11px;color:#8fa3c0;margin-bottom:16px}
hr.divider{border:none;border-top:1px solid #f0f2f5;margin:20px 0}
.snap-ok{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:10px 14px;font-size:12px;color:#166534}
.snap-warn{background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:10px 14px;font-size:12px;color:#9a3412}
[data-testid="stSidebar"]{background:#1a2235!important}
[data-testid="stSidebar"] *{color:white!important}
[data-testid="stSidebar"] input{color:#1a2235!important;background:white!important}
</style>""", unsafe_allow_html=True)

# ---------- PASSWORD ----------
def check_password():
    if st.session_state.get("auth"): return True
    with st.sidebar:
        st.markdown("### 🔐 SLA Dashboard")
        pwd = st.text_input("Κωδικός", type="password", key="pwd_input")
        if pwd:
            if pwd == str(st.secrets.get("APP_PASSWORD","sla2026")):
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Λάθος κωδικός")
    return False

if not check_password():
    st.stop()

# ---------- GITHUB ----------
GH_REPO   = st.secrets.get("github",{}).get("repo","antkanavos/sla-dashboard-v2")
GH_BRANCH = st.secrets.get("github",{}).get("branch","main")
GH_TOKEN  = st.secrets.get("github",{}).get("token","")
GH_RAW    = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}"

def gh_get(path):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}?ref={GH_BRANCH}"
    r = requests.get(url, headers={"Authorization":f"token {GH_TOKEN}"})
    return r.json() if r.ok else None

def gh_put(path, content_str, message, sha=None):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{path}"
    payload = {"message":message,"content":base64.b64encode(content_str.encode()).decode(),"branch":GH_BRANCH}
    if sha: payload["sha"] = sha
    r = requests.put(url, headers={"Authorization":f"token {GH_TOKEN}","Content-Type":"application/json"}, json=payload)
    return r.ok

# ---------- GOOGLE SHEETS ----------
SHEET_ID = st.secrets.get("gsheets",{}).get("spreadsheet_id","1VAdsukayM3JHtCZa7e8eP4Uy_yAIgsXIGWJSY4PwnMM")

def get_gsheet():
    gs = st.secrets["gsheets"]
    creds_dict = {
        "type": gs["type"],
        "project_id": gs["project_id"],
        "private_key_id": gs["private_key_id"],
        "private_key": gs["private_key"],
        "client_email": gs["client_email"],
        "client_id": gs["client_id"],
        "token_uri": gs["token_uri"],
    }
    creds = Credentials.from_service_account_info(creds_dict, scopes=[
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).sheet1

def gsheet_backoff(func, *args, **kwargs):
    for attempt in range(6):
        try:
            return func(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(2 ** attempt)
            else:
                raise

@st.cache_data(ttl=60)
def load_master_table():
    try:
        ws   = get_gsheet()
        data = ws.get_all_records(default_blank="")
        if not data:
            return pd.DataFrame(), None
        df = pd.DataFrame(data, dtype=str).replace({"nan":"","NaT":"","None":""})
        return df, None
    except Exception as e:
        raise RuntimeError(f"Αποτυχία ανάγνωσης Google Sheet: {e}")

# ---------- HELPERS ----------
@st.cache_data(ttl=3600)
def load_customers():
    try:
        return pd.read_csv(f"{GH_RAW}/customers.csv", dtype=str)
    except:
        return pd.DataFrame(columns=["Customer No.","Customer Name"])



def normalize_date(d):
    if not d or str(d).strip() in ("","nan","NaT","None"): return ""
    try:
        parsed = pd.to_datetime(str(d), dayfirst=True, errors="coerce")
        if pd.isna(parsed): return ""
        return parsed.strftime("%d/%m/%Y")
    except:
        return str(d).strip()

def parse_date_robust(series):
    s = series.astype(str).str.strip().str.lstrip("'").replace({"":"NaT","nan":"NaT","None":"NaT","NaT":"NaT"})
    iso_mask = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    parsed = pd.Series(pd.NaT, index=s.index)
    if iso_mask.any():
        parsed[iso_mask] = pd.to_datetime(s[iso_mask], errors="coerce")
    non_iso = ~iso_mask & (s != "NaT")
    if non_iso.any():
        parsed[non_iso] = pd.to_datetime(s[non_iso], dayfirst=True, errors="coerce")
    return parsed

def to_bool(series):
    return series.astype(str).str.strip().str.upper().isin(["TRUE","1","YES"])

# ---------- MASTER TABLE SCHEMA ----------
MT_COLS = [
    "Consignment No.","Date of Pickup","Date of First Attempt","Date of Delivery","Date of Return",
    "Customer No.","Customer Agreement","Delivery Depot","Delivery Region Type",
    "Delivery Land","Delivery Remote","Delivery Inaccessible",
    "First Attempt","First Attempt Days","Returned","Returned Days",
    "Delivered","Delivered Days","First Attempt in SLA","Return in SLA"
]

# ---------- UPDATE MASTER TABLE ----------
def update_master_table(df_new):
    load_master_table.clear()
    existing, _ = load_master_table()

    # Get current SHA for data.csv
    gh_info = gh_get("data.csv")
    sha = gh_info.get("sha") if gh_info else None

    # Filter out rows where no consignment number
    df_new = df_new.copy()
    consignment_col = "Consignment No."
    if consignment_col not in df_new.columns:
        return existing, 0, 0, False, sha

    df_new[consignment_col] = df_new[consignment_col].astype(str).str.strip()
    df_new = df_new[df_new[consignment_col].notna() & (df_new[consignment_col] != "") & (df_new[consignment_col] != "nan")]

    if df_new.empty:
        return existing, 0, 0, False, sha

    # Normalize date columns
    date_cols = ["Date of Pickup","Date of First Attempt","Date of Delivery","Date of Return"]
    for col in date_cols:
        if col in df_new.columns:
            df_new[col] = df_new[col].apply(normalize_date)

    if existing.empty:
        # Sheet has only headers — insert all rows from data.csv
        rows_to_add = []
        for _, row in df_new.iterrows():
            r = {}
            for col in MT_COLS:
                val = str(row.get(col,"")).strip() if col in df_new.columns else ""
                if "Date" in col:
                    val = normalize_date(val)
                r[col] = val
            rows_to_add.append(r)
        if rows_to_add:
            ws = get_gsheet()
            new_df = pd.DataFrame(rows_to_add)
            new_rows = new_df[MT_COLS].fillna("").astype(str).values.tolist()
            for i in range(0, len(new_rows), 500):
                gsheet_backoff(ws.append_rows, new_rows[i:i+500], value_input_option="RAW")
            load_master_table.clear()
        return pd.DataFrame(), len(rows_to_add), 0, len(rows_to_add)>0, sha

    existing_ids = set(existing[consignment_col].astype(str).str.strip().tolist())

    # New rows
    new_mask = ~df_new[consignment_col].isin(existing_ids)
    new_rows_df = df_new[new_mask].copy()

    # Build rows to append
    rows_to_add = []
    for _, row in new_rows_df.iterrows():
        r = {}
        for col in MT_COLS:
            r[col] = str(row.get(col,"")).strip() if col in df_new.columns else ""
        rows_to_add.append(r)

    n_new = len(rows_to_add)

    # Updates: existing rows where First Attempt or Delivery changed
    existing_idx = {str(r).strip(): i+2 for i, r in enumerate(existing[consignment_col].tolist())}
    rows_updated = []
    for _, row in df_new[~new_mask].iterrows():
        cno = str(row[consignment_col]).strip()
        ex_row = existing[existing[consignment_col].astype(str).str.strip() == cno]
        if ex_row.empty: continue
        ex = ex_row.iloc[0]
        new_fa = normalize_date(str(row.get("Date of First Attempt","")))
        new_del = normalize_date(str(row.get("Date of Delivery","")))
        new_ret = normalize_date(str(row.get("Date of Return","")))
        ex_fa  = str(ex.get("Date of First Attempt","")).strip()
        ex_del = str(ex.get("Date of Delivery","")).strip()
        if new_fa and new_fa != ex_fa:
            rows_updated.append((cno, row, existing_idx.get(cno)))
        elif new_del and new_del != ex_del:
            rows_updated.append((cno, row, existing_idx.get(cno)))

    n_updated = len(rows_updated)
    changed = n_new > 0 or n_updated > 0

    ws = get_gsheet()

    # Append new rows
    if rows_to_add:
        new_df = pd.DataFrame(rows_to_add)
        new_rows = new_df[MT_COLS].fillna("").astype(str).values.tolist()
        for i in range(0, len(new_rows), 500):
            gsheet_backoff(ws.append_rows, new_rows[i:i+500], value_input_option="RAW")

    # Batch update changed rows
    if rows_updated:
        col_map = {col: i+1 for i, col in enumerate(MT_COLS)}
        batch = []
        for cno, row, sheet_row in rows_updated:
            if not sheet_row: continue
            for col in MT_COLS:
                val = normalize_date(str(row.get(col,""))) if "Date" in col else str(row.get(col,"")).strip()
                col_letter = chr(64 + col_map[col]) if col_map[col] <= 26 else "A"+chr(64+col_map[col]-26)
                batch.append({"range": f"{col_letter}{sheet_row}", "values": [[val]]})
        if batch:
            for i in range(0, len(batch), 500):
                gsheet_backoff(ws.batch_update, batch[i:i+500])

    load_master_table.clear()
    return existing, n_new, n_updated, changed, sha

# ---------- LOAD & PROCESS ----------
@st.cache_data(ttl=120)
def load_and_process():
    mt, _ = load_master_table()

    if mt is None or len(mt) == 0:
        return pd.DataFrame()

    df = mt.rename(columns={"Date of Pickup": "Ημ/νία Pickup"}, inplace=False).copy()

    # Parse dates
    for col in ["Ημ/νία Pickup","Date of First Attempt","Date of Delivery","Date of Return"]:
        if col in df.columns:
            df[col] = parse_date_robust(df[col])
        else:
            df[col] = pd.NaT

    # Boolean columns
    for col in ["First Attempt","Returned","Delivered","First Attempt in SLA","Return in SLA","Delivery Land","Delivery Remote","Delivery Inaccessible"]:
        if col in df.columns:
            df[col] = to_bool(df[col])
        else:
            df[col] = False

    # Numeric columns
    for col in ["First Attempt Days","Returned Days","Delivered Days"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df

# ---------- METRICS ----------
def metrics(df):
    today = pd.Timestamp(date.today())
    total = len(df)
    n_fa      = int(df["First Attempt"].sum())
    n_del     = int(df["Delivered"].sum())
    n_ret     = int(df["Returned"].sum())
    n_in_sla  = int(df["First Attempt in SLA"].sum())
    sla_pct   = n_in_sla / total * 100 if total else 0
    n_pending = int(df["Date of First Attempt"].isna().sum())
    return total, n_fa, n_del, n_ret, n_in_sla, sla_pct, n_pending

# ---------- SIDEBAR ----------
with st.sidebar:
    st.markdown("## 📦 SLA Dashboard")
    st.markdown("---")
    st.markdown("### ΠΛΟΗΓΗΣΗ")
    page = st.radio("", ["Επισκόπηση","Ανάλυση Νομού","Ανάλυση Καταστήματος"], label_visibility="collapsed")

# ---------- UPDATE SHEET (before load) ----------
try:
    _df_csv = pd.read_csv(f"{GH_RAW}/data.csv")
    update_master_table(_df_csv)
except Exception:
    pass  # silent — show error in snapshot section

# ---------- LOAD DATA ----------
try:
    df_full = load_and_process()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if df_full is None or len(df_full) == 0:
    st.error("Δεν βρέθηκαν δεδομένα.")
    st.stop()

_pickup_valid = df_full["Ημ/νία Pickup"].dropna()
if len(_pickup_valid) == 0:
    st.error("Δεν βρέθηκαν έγκυρες ημερομηνίες Pickup.")
    st.stop()

min_d = _pickup_valid.min().date()
max_d = _pickup_valid.max().date()

# ---------- CUSTOMERS / AGREEMENTS ----------
customers_df = load_customers()

# Build customer map: No. → Name
cust_map = {}
if len(customers_df) and "Customer No." in customers_df.columns and "Customer Name" in customers_df.columns:
    for _, r in customers_df.iterrows():
        cust_map[str(r["Customer No."]).strip()] = str(r["Customer Name"]).strip()

# ---------- TOP FILTERS ----------
fc1, fc2 = st.columns(2)

# Customer filter
all_customers = sorted(df_full["Customer No."].dropna().astype(str).str.strip().unique().tolist())
cust_options = {"Όλοι": "Όλοι"}
for c in all_customers:
    label = f"{cust_map[c]} ({c})" if c in cust_map else c
    cust_options[label] = c

with fc1:
    sel_cust_label = st.selectbox("Πελάτης", list(cust_options.keys()), key="sel_cust")
sel_cust = cust_options[sel_cust_label]

# Agreement filter — filtered by selected customer from df_full
if sel_cust == "Όλοι":
    agr_pool = df_full
else:
    agr_pool = df_full[df_full["Customer No."].astype(str).str.strip() == sel_cust]

agr_options = {"Όλες": "Όλες"}
for code in sorted(agr_pool["Customer Agreement"].dropna().astype(str).str.strip().unique().tolist()):
    if code and code != "nan":
        agr_options[code] = code

with fc2:
    sel_agr_label = st.selectbox("Συμφωνία", list(agr_options.keys()), key="sel_agr")
sel_agr = agr_options[sel_agr_label]

# Date filters
dc1, dc2 = st.columns(2)
with dc1:
    date_from = st.date_input("Από", value=min_d, min_value=min_d, max_value=max_d, key="ep_df", format="DD/MM/YYYY")
with dc2:
    date_to   = st.date_input("Έως", value=max_d, min_value=min_d, max_value=max_d, key="ep_dt", format="DD/MM/YYYY")

# Apply filters
df = df_full.copy()
if sel_cust != "Όλοι":
    df = df[df["Customer No."].astype(str).str.strip() == sel_cust]
if sel_agr != "Όλες":
    df = df[df["Customer Agreement"].astype(str).str.strip() == sel_agr]
df = df[(df["Ημ/νία Pickup"].dt.date >= date_from) & (df["Ημ/νία Pickup"].dt.date <= date_to)]

# ════════════════════════════════════
# ΕΠΙΣΚΟΠΗΣΗ
# ════════════════════════════════════
if page == "Επισκόπηση":

    total, n_fa, n_del, n_ret, n_in_sla, sla_pct, n_pending = metrics(df)

    # KPI cards
    k1,k2,k3,k4,k5,k6,k7 = st.columns(7)
    kpis = [
        (k1,"📦","ΣΥΝΟΛΟ",          f"{total:,}",      "100%"),
        (k2,"✅","FIRST ATTEMPT",    f"{n_fa:,}",       f"{n_fa/total*100:.1f}% του συνόλου" if total else ""),
        (k3,"🚚","DELIVERED",        f"{n_del:,}",      f"{n_del/total*100:.1f}% του συνόλου" if total else ""),
        (k4,"↩️","RETURNED",         f"{n_ret:,}",      f"{n_ret/total*100:.1f}% του συνόλου" if total else ""),
        (k5,"🎯","ΕΝΤΟΣ SLA",        f"{n_in_sla:,}",   f"{sla_pct:.2f}% του συνόλου"),
        (k6,"📊","SLA %",            f"{sla_pct:.2f}%", f"{n_in_sla:,} / {total:,}"),
        (k7,"⏳","PENDING",          f"{n_pending:,}",  f"{n_pending/total*100:.1f}% του συνόλου" if total else ""),
    ]
    for col, icon, lbl, val, sub in kpis:
        with col:
            st.markdown(f"""<div class="kpi-card">
                <div class="kpi-label">{icon} {lbl}</div>
                <div class="kpi-value">{val}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Zone analysis
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΖΩΝΗ ΠΑΡΑΔΟΣΗΣ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">(ΟΛΟ ΤΟ ΔΙΑΣΤΗΜΑ)</div>', unsafe_allow_html=True)

    zone_cols = st.columns(3)
    for i, (zone_col, zone_lbl, color) in enumerate([
        ("Delivery Land","Land","#22c55e"),
        ("Delivery Remote","Remote","#f97316"),
        ("Delivery Inaccessible","Inaccessible","#7c3aed")
    ]):
        zdf = df[df[zone_col].fillna(False)] if zone_col in df.columns else pd.DataFrame()
        with zone_cols[i]:
            if not len(zdf):
                st.markdown(f'<div class="kpi-card"><div class="kpi-label">{zone_lbl}</div><div class="kpi-value" style="color:#ccc">—</div></div>', unsafe_allow_html=True)
                continue
            z_total = len(zdf)
            z_in_sla = int(zdf["First Attempt in SLA"].sum())
            z_pct = z_in_sla / z_total * 100 if z_total else 0
            z_out = z_total - z_in_sla
            r = 62; cx = cy = 78; stroke = 16; circ = 2*3.14159*r
            filled = circ*z_pct/100; gap = circ-filled
            svg = f"""<svg viewBox="0 0 156 156" width="160" height="160">
                <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#f1f5f9" stroke-width="{stroke}"/>
                <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}"
                    stroke-dasharray="{filled:.2f} {gap:.2f}" stroke-linecap="round" transform="rotate(-90 {cx} {cy})"/>
                <text x="{cx}" y="{cy-8}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="22" font-weight="800" fill="#1a2235">{z_pct:.1f}%</text>
                <text x="{cx}" y="{cy+12}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="10" fill="#8fa3c0">εντός SLA</text>
            </svg>"""
            st.markdown(f"""<div class="kpi-card" style="display:flex;align-items:center;gap:16px;">
                {svg}
                <div>
                    <div class="kpi-label" style="margin-bottom:8px">{zone_lbl}</div>
                    <div style="font-size:12px;margin-bottom:4px;color:#1a2235">
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:6px"></span>
                        Εντός <b>{z_in_sla:,}</b> ({z_pct:.1f}%)
                    </div>
                    <div style="font-size:12px;margin-bottom:12px;color:#1a2235">
                        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#fca5a5;margin-right:6px"></span>
                        Εκτός <b>{z_out:,}</b> ({100-z_pct:.1f}%)
                    </div>
                    <div class="kpi-sub">Σύνολο: {z_total:,}</div>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Delay analysis (εκτός SLA)
    st.markdown('<div class="section-header">ΚΑΘΥΣΤΕΡΗΣΗ ΠΑΡΑΔΟΣΕΩΝ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">(ΟΛΟ ΤΟ ΔΙΑΣΤΗΜΑ)</div>', unsafe_allow_html=True)

    out_sla = df[df["First Attempt"].fillna(False) & ~df["First Attempt in SLA"].fillna(False)].copy()
    n_out = len(out_sla)

    def delay_donut_svg(count, z1, z2, z3, size=160):
        r=62; cx=cy=78; stroke=16; circ=2*3.14159*r
        total = z1+z2+z3 if (z1+z2+z3)>0 else 1
        s1=circ*z1/total; s2=circ*z2/total; s3=circ*z3/total
        def arc(color, dashlen, offset_deg):
            gap=circ-dashlen
            return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-dasharray="{dashlen:.2f} {gap:.2f}" stroke-linecap="butt" transform="rotate({offset_deg} {cx} {cy})"/>'
        deg1=-90; deg2=deg1+360*z1/total; deg3=deg2+360*z2/total
        svg = f'<svg viewBox="0 0 156 156" width="{size}" height="{size}" style="flex-shrink:0;">'
        svg += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#f1f5f9" stroke-width="{stroke}"/>'
        if z1>0: svg += arc("#22c55e",s1,deg1)
        if z2>0: svg += arc("#f97316",s2,deg2)
        if z3>0: svg += arc("#7c3aed",s3,deg3)
        svg += f'<text x="{cx}" y="{cy-6}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="22" font-weight="800" fill="#1a2235">{count:,}</text>'
        svg += f'<text x="{cx}" y="{cy+16}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="10" font-weight="600" fill="#8fa3c0">αποστολές</text>'
        svg += '</svg>'
        return svg

    delay_cols_ui = st.columns(3)
    delay_bands = [
        (1,2,"1 ΗΜΕΡΑ ΚΑΘΥΣΤΕΡΗΣΗ"),
        (2,3,"2 ΗΜΕΡΕΣ ΚΑΘΥΣΤΕΡΗΣΗ"),
        (3,999,"3+ ΗΜΕΡΕΣ ΚΑΘΥΣΤΕΡΗΣΗ"),
    ]
    for i, (d_min, d_max, lbl) in enumerate(delay_bands):
        with delay_cols_ui[i]:
            if not n_out:
                st.markdown(f'<div class="kpi-card" style="text-align:center;color:#ccc">{lbl}<br>Δεν υπάρχουν δεδομένα</div>', unsafe_allow_html=True)
                continue
            grp = out_sla[(out_sla["First Attempt Days"] >= d_min) & (out_sla["First Attempt Days"] < d_max)]
            cnt = len(grp)
            pct = cnt/total*100 if total else 0
            z1 = int(grp["Delivery Land"].sum()) if "Delivery Land" in grp.columns else 0
            z2 = int(grp["Delivery Remote"].sum()) if "Delivery Remote" in grp.columns else 0
            z3 = int(grp["Delivery Inaccessible"].sum()) if "Delivery Inaccessible" in grp.columns else 0
            zt = z1+z2+z3 if (z1+z2+z3)>0 else 1
            st.markdown(f"""<div class="kpi-card" style="display:flex;align-items:center;gap:16px;">
                {delay_donut_svg(cnt,z1,z2,z3)}
                <div style="flex:1">
                    <div class="kpi-label" style="margin-bottom:12px">{lbl}</div>
                    <div style="font-size:12px;margin-bottom:4px;color:#1a2235"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:6px"></span>Land <b>{z1:,}</b> <span style="color:#8fa3c0">({z1/zt*100:.1f}%)</span></div>
                    <div style="font-size:12px;margin-bottom:4px;color:#1a2235"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f97316;margin-right:6px"></span>Remote <b>{z2:,}</b> <span style="color:#8fa3c0">({z2/zt*100:.1f}%)</span></div>
                    <div style="font-size:12px;margin-bottom:12px;color:#1a2235"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#7c3aed;margin-right:6px"></span>Inaccessible <b>{z3:,}</b> <span style="color:#8fa3c0">({z3/zt*100:.1f}%)</span></div>
                    <div class="kpi-sub">% επί παραδοθέντων</div>
                    <div style="font-size:16px;font-weight:800;color:#1a2235">{pct:.1f}%</div>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Monthly performance
    st.markdown('<div class="section-header">ΜΗΝΙΑΙΑ ΕΠΙΔΟΣΗ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">(ΤΕΛΕΥΤΑΙΟΙ 3 ΗΜΕΡΟΛΟΓΙΑΚΟΙ ΜΗΝΕΣ)</div>', unsafe_allow_html=True)

    MONTH_GR = ["","ΙΑΝΟΥΑΡΙΟΣ","ΦΕΒΡΟΥΑΡΙΟΣ","ΜΑΡΤΙΟΣ","ΑΠΡΙΛΙΟΣ","ΜΑΪΟΣ","ΙΟΥΝΙΟΣ",
                "ΙΟΥΛΙΟΣ","ΑΥΓΟΥΣΤΟΣ","ΣΕΠΤΕΜΒΡΙΟΣ","ΟΚΤΩΒΡΙΟΣ","ΝΟΕΜΒΡΙΟΣ","ΔΕΚΕΜΒΡΙΟΣ"]
    today = date.today()
    months = []
    for delta in range(2,-1,-1):
        m = today.month - delta
        y = today.year
        while m <= 0: m += 12; y -= 1
        is_cur = (y == today.year and m == today.month)
        months.append((y,m,is_cur))

    mo_cols = st.columns(3)
    for col_i, (yr,mo,is_current) in enumerate(months):
        mask = (df["Ημ/νία Pickup"].dt.year == yr) & (df["Ημ/νία Pickup"].dt.month == mo)
        sub = df[mask]
        with mo_cols[col_i]:
            lbl = f"{MONTH_GR[mo]} {yr}"
            if is_current:
                lbl += f" (ΕΩΣ {today.strftime('%d/%m')})"
            if not len(sub):
                st.markdown(f'<div class="kpi-card"><div class="kpi-label">{lbl}</div><div style="color:#ccc;margin-top:8px">Δεν υπάρχουν δεδομένα</div></div>', unsafe_allow_html=True)
                continue
            mo_total = len(sub)
            mo_in_sla = int(sub["First Attempt in SLA"].sum())
            mo_pct = mo_in_sla/mo_total*100 if mo_total else 0
            pct_color = "#22c55e" if mo_pct>=90 else "#f97316" if mo_pct>=75 else "#ef4444"
            zone_rows = ""
            for zcol, zlbl, zcolor in [("Delivery Land","Land","#22c55e"),("Delivery Remote","Remote","#f97316"),("Delivery Inaccessible","Inaccessible","#7c3aed")]:
                zg = sub[sub[zcol]] if zcol in sub.columns else pd.DataFrame()
                if not len(zg): continue
                zpct = int(zg["First Attempt in SLA"].sum())/len(zg)*100
                zc = "#22c55e" if zpct>=90 else "#f97316" if zpct>=75 else "#ef4444"
                zone_rows += (
                    '<div style="margin-bottom:10px;">'
                    '<div style="display:flex;justify-content:space-between;font-size:11px;color:#8fa3c0;margin-bottom:3px;">'
                    f'<span>{zlbl}</span><span style="font-weight:700;color:{zc};">{zpct:.2f}%</span>'
                    '</div>'
                    '<div style="background:#f1f5f9;border-radius:4px;height:6px;">'
                    f'<div style="background:{zc};width:{min(100,zpct):.1f}%;height:6px;border-radius:4px;"></div>'
                    '</div></div>'
                )
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-label" style="text-transform:uppercase;margin-bottom:6px">{lbl}</div>'
                f'<div style="font-size:10px;color:#8fa3c0;margin-bottom:4px">SLA % (ΕΝΤΟΣ)</div>'
                f'<div style="font-size:30px;font-weight:800;color:{pct_color};margin-bottom:2px">{mo_pct:.2f}%</div>'
                f'<div style="font-size:11px;color:#8fa3c0;margin-bottom:16px">{mo_in_sla:,} / {mo_total:,}</div>'
                f'{zone_rows}</div>',
                unsafe_allow_html=True
            )

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Snapshot section
    st.markdown('<div class="section-header">ΕΝΗΜΕΡΩΣΗ ΔΕΔΟΜΕΝΩΝ</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Αυτόματο snapshot κάθε φορά που ανεβαίνει νέο data.csv</div>', unsafe_allow_html=True)

    try:
        df_new_data = pd.read_csv(f"{GH_RAW}/data.csv")
        existing_before, _ = load_master_table()
        n_existing = len(existing_before) if existing_before is not None else 0
        try:
            _, n_new, n_updated, changed, _ = update_master_table(df_new_data)
            existing_after, _ = load_master_table()
            n_after = len(existing_after) if existing_after is not None else 0
            if changed:
                load_and_process.clear()
                st.markdown(f'<div class="snap-ok">✅ Νέο snapshot: <b>{n_new}</b> νέες αποστολές, <b>{n_updated}</b> ενημερώθηκαν</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="snap-ok">✅ Καμία αλλαγή — δεν χρειάζεται νέο snapshot</div>', unsafe_allow_html=True)
        except RuntimeError as e:
            st.markdown(f'<div class="snap-warn">⚠️ {e}</div>', unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f'<div class="snap-warn">⚠️ Αδυναμία ανάγνωσης data.csv: {e}</div>', unsafe_allow_html=True)

# ════════════════════════════════════
# ΑΝΑΛΥΣΗ ΝΟΜΟΥ
# ════════════════════════════════════
elif page == "Ανάλυση Νομού":
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΝΟΜΟ</div>', unsafe_allow_html=True)

    def period_stats(d_from, d_to):
        sub = df[(df["Ημ/νία Pickup"].dt.date >= d_from) & (df["Ημ/νία Pickup"].dt.date <= d_to)]
        if not len(sub): return pd.DataFrame()
        grp = sub.groupby("Delivery Depot").agg(
            total=("Consignment No.","count"),
            in_sla=("First Attempt in SLA","sum"),
        ).reset_index()
        grp["sla_pct"] = (grp["in_sla"]/grp["total"]*100).round(2)
        return grp.sort_values("total", ascending=False)

    dc1,dc2 = st.columns(2)
    with dc1: d_from = st.date_input("Από",value=min_d,min_value=min_d,max_value=max_d,key="nm_df",format="DD/MM/YYYY")
    with dc2: d_to   = st.date_input("Έως",value=max_d,min_value=min_d,max_value=max_d,key="nm_dt",format="DD/MM/YYYY")

    grp = period_stats(d_from, d_to)
    if len(grp):
        fig = go.Figure(go.Bar(
            x=grp["Delivery Depot"], y=grp["sla_pct"],
            marker_color=grp["sla_pct"].apply(lambda x: "#22c55e" if x>=90 else "#f97316" if x>=75 else "#ef4444"),
            text=grp["sla_pct"].apply(lambda x: f"{x:.1f}%"), textposition="outside"
        ))
        fig.update_layout(height=400, paper_bgcolor="white", plot_bgcolor="white",
            margin=dict(t=20,b=40,l=40,r=20), yaxis=dict(range=[0,115],ticksuffix="%",gridcolor="#f0f2f5"),
            showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Δεν υπάρχουν δεδομένα για το επιλεγμένο διάστημα.")

# ════════════════════════════════════
# ΑΝΑΛΥΣΗ ΚΑΤΑΣΤΗΜΑΤΟΣ
# ════════════════════════════════════
elif page == "Ανάλυση Καταστήματος":
    st.markdown('<div class="section-header">ΑΝΑΛΥΣΗ ΑΝΑ ΚΑΤΑΣΤΗΜΑ</div>', unsafe_allow_html=True)

    dc1,dc2 = st.columns(2)
    with dc1: d_from = st.date_input("Από",value=min_d,min_value=min_d,max_value=max_d,key="sh_df",format="DD/MM/YYYY")
    with dc2: d_to   = st.date_input("Έως",value=max_d,min_value=min_d,max_value=max_d,key="sh_dt",format="DD/MM/YYYY")

    sub = df[(df["Ημ/νία Pickup"].dt.date >= d_from) & (df["Ημ/νία Pickup"].dt.date <= d_to)]
    if len(sub):
        grp = sub.groupby("Delivery Depot").agg(
            total=("Consignment No.","count"),
            in_sla=("First Attempt in SLA","sum"),
        ).reset_index()
        grp["sla_pct"] = (grp["in_sla"]/grp["total"]*100).round(2)
        grp = grp.sort_values("sla_pct", ascending=True)

        for _, row in grp.iterrows():
            pct = row["sla_pct"]
            color = "#22c55e" if pct>=90 else "#f97316" if pct>=75 else "#ef4444"
            st.markdown(
                f'<div class="kpi-card" style="margin-bottom:8px;display:flex;align-items:center;gap:16px;">'
                f'<div style="min-width:140px;font-size:13px;font-weight:600;color:#1a2235">{row["Delivery Depot"]}</div>'
                f'<div style="flex:1;background:#f1f5f9;border-radius:6px;height:8px;">'
                f'<div style="background:{color};width:{min(100,pct):.1f}%;height:8px;border-radius:6px;"></div></div>'
                f'<div style="min-width:60px;text-align:right;font-size:13px;font-weight:700;color:{color}">{pct:.1f}%</div>'
                f'<div style="min-width:60px;text-align:right;font-size:11px;color:#8fa3c0">{int(row["total"]):,}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Δεν υπάρχουν δεδομένα για το επιλεγμένο διάστημα.")
