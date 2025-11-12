from pathlib import Path
import pandas as pd
import numpy as np
import re
from datetime import datetime
import warnings

print("A EXECUTAR:", __file__)

warnings.filterwarnings(
    "ignore",
    message="Could not infer format, so each element will be parsed individually"
)

# Helpers
def str_clean(s):
    return pd.Series(s, dtype="object").astype(str).str.strip()

def to_num_pt(x: pd.Series) -> pd.Series:
    s = pd.to_numeric(x, errors="coerce")
    mask = s.isna()
    if mask.any():
        s2 = (pd.Series(x, dtype="object")[mask]
              .astype(str)
              .str.replace(r"[^\d,.\-+]", "", regex=True)
              .str.replace(".", "", regex=False)
              .str.replace(",", ".", regex=False))
        s.loc[mask] = pd.to_numeric(s2, errors="coerce")
    return s.astype(float)

def _looks_like_cents(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return False
    frac_part = (s.abs() % 1.0)
    frac_zero_ratio = (frac_part < 1e-9).mean()
    med = s.abs().median()
    p95 = s.abs().quantile(0.95)
    return (frac_zero_ratio >= 0.90) and (med >= 1_000 or p95 >= 10_000)

def normalize_amount_series(s: pd.Series) -> pd.Series:
    snum = pd.to_numeric(s, errors="coerce")
    if _looks_like_cents(snum):
        snum = snum / 100.0
    return snum.fillna(0.0)

# Heurística específica para ficheiros de CHARGES (valores muitas vezes em cêntimos inteiros)
def normalize_amount_series_charges(s: pd.Series) -> pd.Series:
    snum = pd.to_numeric(s, errors="coerce")
    z = snum.dropna().abs()
    if z.empty:
        return snum.fillna(0.0)
    frac_zero_ratio = ((z % 1.0) < 1e-9).mean()
    med = z.median()
    # Se praticamente todos são inteiros e a mediana já é "escala cêntimos" (>=100), divide por 100
    if frac_zero_ratio >= 0.90 and med >= 100:
        snum = snum / 100.0
    return snum.fillna(0.0)

def encontrar_coluna(df: pd.DataFrame, candidatos, excluir=None) -> str | None:
    cols = list(df.columns)
    lowers = {c.lower(): c for c in cols}
    excluir = [e.lower() for e in (excluir or [])]

    def _ok(name: str) -> bool:
        l = name.lower()
        return all(e not in l for e in excluir)

    for pat in candidatos:
        k = pat.lower()
        if k in lowers and _ok(lowers[k]):
            return lowers[k]
    for pat in candidatos:
        rx = re.compile(rf"\b{re.escape(pat)}\b", flags=re.I)
        for c in cols:
            if rx.search(c) and _ok(c):
                return c
    for pat in candidatos:
        p = pat.lower()
        for c in cols:
            if p in c.lower() and _ok(c):
                return c
    return None

def escolher_coluna_data_transacoes(df: pd.DataFrame) -> str | None:
    return encontrar_coluna(
        df,
        candidatos=[
            "PAYOUT_DATE","PAYMENT_DATE",
            "Date","Datetime","Created_at","Processed date","Event date","Timestamp","Processed","created at"
        ],
        excluir=["Expiration date"]
    )

def ler_qualquer_tabela(p: Path) -> pd.DataFrame:
    s = p.suffix.lower()
    if s in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if s in (".csv", ".txt"):
        try:
            return pd.read_csv(p, sep=";", engine="python")
        except Exception:
            pass
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return pd.read_csv(p, sep=None, engine="python", encoding=enc)
            except Exception:
                continue
        return pd.read_csv(p, sep=None, engine="python", encoding_errors="ignore")
    raise ValueError(f"Formato não suportado: {p}")

def _listar_ficheiros(dir_path: Path):
    return [p for p in dir_path.rglob("*")
            if p.is_file() and p.suffix.lower() in (".csv",".txt",".xlsx",".xls")]

def dentro_intervalo(d: pd.Series, lo, hi) -> pd.Series:
    return (d >= lo) & (d <= hi)

def series_by_date(df: pd.DataFrame, date_col: str, val_col: str, idx) -> pd.Series:
    if df.empty:
        return pd.Series(0.0, index=idx)
    dates = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    s = (df.assign(_d=dates)
           .dropna(subset=["_d"])
           .groupby("_d")[val_col].sum())
    return s.reindex(idx, fill_value=0.0)

# Caminhos e ficheiros
BASE = Path(r"C:\Users\MargaridaDias\TML\Gestão de Contratos - Documents\General\ISO\Projetos\CUT")
DIR_TRANS_ALL   = BASE / "Transactions" / "10_outubro"
DIR_CHARGES_ALL = BASE / "Charges"     / "10_outubro"
DIR_RECON       = BASE / "Reconciliation"
DIR_CONTA       = BASE / "Valores_conta"
DIR_FATURAS     = BASE / "Faturas"
F_TARIFAS       = BASE / "Tarifas.xlsx"

F_OUT_09  = BASE / r"Analises\Analise_Transactions_10.xlsx"
F_OUT_SUM = BASE / r"Analises\Quadro_Sintese_10.xlsx"

# Janela temporal (baseada nas Transactions)
def carregar_transactions_sem_filtro(dir_path: Path) -> pd.DataFrame:
    files = _listar_ficheiros(dir_path)
    frames=[]
    for f in files:
        raw = ler_qualquer_tabela(f)
        c_ts    = escolher_coluna_data_transacoes(raw)
        c_line  = encontrar_coluna(raw, ["line","linha","route"])
        c_veh   = encontrar_coluna(raw, ["vehicle","viatura"])
        c_pan   = encontrar_coluna(raw, ["card pan","cardpan","masked","pan"])
        c_token = encontrar_coluna(raw, ["card token","token","transaction id"])

        ts_raw = raw[c_ts] if c_ts else pd.Series([None]*len(raw))
        ts_dt  = pd.to_datetime(ts_raw, errors="coerce")

        frames.append(pd.DataFrame({
            "Ts_raw":     str_clean(ts_raw) if c_ts else pd.Series([""]*len(raw)),
            "Ts":         ts_dt,
            "Line":       str_clean(raw[c_line]) if c_line else np.nan,
            "Vehicle":    str_clean(raw[c_veh]) if c_veh else np.nan,
            "CardPan":    str_clean(raw[c_pan]) if c_pan else np.nan,
            "Card Token": str_clean(raw[c_token]) if c_token else np.nan,
        }))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["Ts_raw","Ts","Line","Vehicle","CardPan","Card Token"])
    out = out.dropna(subset=["Ts"]).copy()
    return out

_trans_all = carregar_transactions_sem_filtro(DIR_TRANS_ALL)
if _trans_all.empty:
    HOJE = pd.Timestamp.today().normalize()
    DT_MIN = HOJE.replace(day=1)
    DT_MAX = HOJE + pd.offsets.MonthEnd(0)
else:
    dmin = _trans_all["Ts"].min().normalize()
    dmax = _trans_all["Ts"].max().normalize()
    DT_MIN = dmin.replace(day=1)
    DT_MAX = dmax + pd.offsets.MonthEnd(0)

FORCE_START = pd.Timestamp("2025-07-23")
INICIO = max(DT_MIN, FORCE_START)
FIM    = min(DT_MAX, pd.Timestamp.today().normalize())

IDX_DIAS   = pd.date_range(INICIO, FIM, freq="D")

# Carregamentos principais
def carregar_transactions(dir_path: Path) -> pd.DataFrame:
    files = _listar_ficheiros(dir_path)
    frames=[]
    for f in files:
        raw = ler_qualquer_tabela(f)
        c_ts     = escolher_coluna_data_transacoes(raw)
        c_line   = encontrar_coluna(raw, ["line","linha","route"])
        c_veh    = encontrar_coluna(raw, ["vehicle","viatura"])
        c_pan    = encontrar_coluna(raw, ["card pan","cardpan","masked","pan"])
        c_token  = encontrar_coluna(raw, ["card token","token","transaction id"])
        c_tstat  = encontrar_coluna(raw, ["transaction status","status"])

        ts_raw = raw[c_ts] if c_ts else pd.Series([None]*len(raw))
        ts_dt  = pd.to_datetime(ts_raw, errors="coerce")

        df = pd.DataFrame({
            "Ts_raw":             str_clean(ts_raw) if c_ts else pd.Series([""]*len(raw)),
            "Ts":                 ts_dt,
            "Line":               str_clean(raw[c_line]) if c_line else np.nan,
            "Vehicle":            str_clean(raw[c_veh]) if c_veh else np.nan,
            "CardPan":            str_clean(raw[c_pan]) if c_pan else np.nan,
            "Card Token":         str_clean(raw[c_token]) if c_token else np.nan,
            "Transaction status": str_clean(raw[c_tstat]) if c_tstat else np.nan,
        })
        frames.append(df)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["Ts_raw","Ts","Line","Vehicle","CardPan","Card Token","Transaction status"]
    )
    out = out.dropna(subset=["Ts"]).copy()

    if "Transaction status" in out.columns:
        excluir = {"nok - rejected acv", "used for debt recovery", "error"}
        out = out[~out["Transaction status"].str.lower().isin(excluir)].copy()

    out = out[(out["Ts"] >= INICIO) & (out["Ts"] <= (FIM + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)))].copy()

    out = out.sort_values(["Line", "Vehicle", "CardPan", "Ts"])
    out["_dt"] = out.groupby(["Line", "Vehicle", "CardPan"])["Ts"].diff().dt.total_seconds()
    out = out[(out["_dt"].isna()) | (out["_dt"] >= 30)].drop(columns=["_dt"])

    out["Intervalo"] = out["Ts"].dt.floor("30s")

    if not out.empty:
        dias = out["Ts"].dt.normalize().nunique()
        print("Transactions carregadas — intervalo:",
              out["Ts"].min(), "→", out["Ts"].max(),
              "| dias distintos:", dias)
    else:
        print("Transactions: sem registos no intervalo alvo.")
    return out

def carregar_tarifas(path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    sheet = "Resumo_tarifas" if "Resumo_tarifas" in xls.sheet_names else xls.sheet_names[0]
    tf = pd.read_excel(path, sheet_name=sheet)
    c_line = encontrar_coluna(tf, ["line","linha","route"])
    c_val  = encontrar_coluna(tf, ["tarifa","preço","price","fare","amount","valor"])
    df = tf[[c_line, c_val]].copy()
    df.columns = ["Line","Tarifa"]
    df["Line"] = str_clean(df["Line"])
    df["Tarifa"] = to_num_pt(df["Tarifa"])
    return df.dropna(subset=["Line","Tarifa"]).drop_duplicates("Line", keep="last")

def carregar_charges(dir_path: Path) -> pd.DataFrame:
    files = _listar_ficheiros(dir_path)
    frames=[]
    for f in files:
        raw = ler_qualquer_tabela(f)

        c_token  = encontrar_coluna(raw, ["card token","token","transaction id"])
        c_stat   = encontrar_coluna(raw, ["charge status"])
        c_date = (escolher_coluna_data_transacoes(raw)
                  or encontrar_coluna(raw, ["charge date","processed date","processed","date","data"],
                                      excluir=["Expiration date"]))
        c_amt    = encontrar_coluna(raw, ["fare charge amount","amount","charged","price"])
        c_deb_s  = encontrar_coluna(raw, ["debt status"])
        c_deb_a  = encontrar_coluna(raw, ["debt amount"])
        c_deb_r  = encontrar_coluna(raw, ["debt recovered date","recovered date"])
        c_deb_c  = encontrar_coluna(raw, ["debt created date","created date"])
        c_scheme = encontrar_coluna(raw, ["card scheme","scheme","brand"])

        # ajuste específico para Charges (escala em cêntimos)
        fare_eur = normalize_amount_series_charges(to_num_pt(raw[c_amt])) if c_amt else pd.Series([0.0]*len(raw))
        debt_eur = normalize_amount_series_charges(to_num_pt(raw[c_deb_a])) if c_deb_a else pd.Series([0.0]*len(raw))

        date_norm    = pd.to_datetime(raw[c_date], errors="coerce") if c_date else pd.Series([pd.NaT]*len(raw))
        deb_rec_norm = pd.to_datetime(raw[c_deb_r], errors="coerce", dayfirst=True) if c_deb_r else pd.Series([pd.NaT]*len(raw))
        deb_crt_norm = pd.to_datetime(raw[c_deb_c], errors="coerce", dayfirst=True) if c_deb_c else pd.Series([pd.NaT]*len(raw))

        df = pd.DataFrame({
            "Card Token": str_clean(raw[c_token]) if c_token else np.nan,
            "Charge status": str_clean(raw[c_stat]) if c_stat else np.nan,
            "Date": date_norm,
            "_Fare_num_eur": fare_eur,
            "_Debt_num_eur": debt_eur,
            "Debt status": str_clean(raw[c_deb_s]) if c_deb_s else np.nan,
            "Debt recovered date": deb_rec_norm,
            "Debt created date": deb_crt_norm,
            "Card Scheme": str_clean(raw[c_scheme]) if c_scheme else np.nan,
        })
        frames.append(df)

    ch = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not ch.empty:
        for col in ["Date","Debt recovered date","Debt created date"]:
            if col in ch.columns:
                ch.loc[~dentro_intervalo(pd.to_datetime(ch[col], errors="coerce"), INICIO, FIM), col] = pd.NaT
        if "Date" in ch.columns:
            print("Charges carregadas — intervalo:",
                  pd.to_datetime(ch["Date"], errors="coerce").min(), "→",
                  pd.to_datetime(ch["Date"], errors="coerce").max())
    else:
        print("Charges: sem registos no intervalo alvo.")
    return ch

def carregar_reconciliation(dir_root: Path) -> pd.DataFrame:
    files = _listar_ficheiros(dir_root)
    frames=[]
    for f in files:
        raw = ler_qualquer_tabela(f)

        c_date = (encontrar_coluna(raw, ["PAYOUT_DATE"]) or
                  encontrar_coluna(raw, ["payout_date","payout date","payoutdate"]) or
                  encontrar_coluna(raw, ["date","data"]))
        s_date = pd.to_datetime(raw[c_date], errors="coerce") if c_date else pd.Series([pd.NaT]*len(raw))
        s_date = s_date.dt.normalize()

        c_payout = (encontrar_coluna(raw, ["PAYOUT_AMOUNT"]) or
                    encontrar_coluna(raw, ["payout_amount","payout amount"]))
        c_gross  = (encontrar_coluna(raw, ["TRANSACTION_GROSS_AMOUNT"]) or
                    encontrar_coluna(raw, ["transaction_gross_amount","transaction gross amount"]))

        payout = normalize_amount_series(to_num_pt(raw[c_payout])) if c_payout else pd.Series([0.0]*len(raw))
        gross  = normalize_amount_series(to_num_pt(raw[c_gross]))  if c_gross  else pd.Series([0.0]*len(raw))

        df = pd.DataFrame({
            "Payout Date": s_date,
            "Payout Amount": pd.to_numeric(payout, errors="coerce").fillna(0.0),
            "Transaction Gross Amount": pd.to_numeric(gross, errors="coerce").fillna(0.0),
        })
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["Payout Date","Payout Amount","Transaction Gross Amount"])

    recon = pd.concat(frames, ignore_index=True)
    recon["Payout Date"] = pd.to_datetime(recon["Payout Date"], errors="coerce").dt.normalize()
    for c in ["Payout Amount", "Transaction Gross Amount"]:
        recon[c] = pd.to_numeric(recon[c], errors="coerce").fillna(0.0)

    return recon.dropna(subset=["Payout Date"]).copy()

def carregar_faturas(dir_root: Path) -> pd.DataFrame:
    files = [p for p in dir_root.rglob("*") if p.is_file() and p.suffix.lower() in (".csv",".txt",".xlsx",".xls")]
    frames=[]
    for f in files:
        raw = ler_qualquer_tabela(f)
        c_date = encontrar_coluna(raw, ["invoicedate","invoice date","date","data"])
        c_nr   = encontrar_coluna(raw, ["documentnr","document nr","number","nr"])
        c_desc = encontrar_coluna(raw, ["description","descr"])
        c_gross= encontrar_coluna(raw, ["grosstotal","gross total","total","amount","valor"])
        if not (c_date or c_nr or c_desc or c_gross):
            continue
        n = len(raw)

        inv_dt_try = pd.to_datetime(raw[c_date], errors="coerce") if c_date else pd.Series([pd.NaT]*len(raw))
        if inv_dt_try.isna().all() and c_date:
            inv_dt_try = pd.to_datetime(raw[c_date], errors="coerce", dayfirst=True)

        s_amt  = normalize_amount_series(to_num_pt(raw[c_gross])) if c_gross else pd.Series([0.0]*n)

        df = pd.DataFrame({
            "InvoiceDate": inv_dt_try,
            "DocumentNr":  str_clean(raw[c_nr]) if c_nr else pd.Series([""]*n),
            "Description": str_clean(raw[c_desc]) if c_desc else pd.Series([""]*n),
            "GrossTotal":  pd.to_numeric(s_amt, errors="coerce").fillna(0.0),
        })
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["InvoiceDate","InvoiceDate_Date","InvoiceDate_Time","DocumentNr","Description","GrossTotal"])

    fat = pd.concat(frames, ignore_index=True)
    fat = fat.drop_duplicates(subset=["InvoiceDate","DocumentNr"], keep="last")
    fat["InvoiceDate"] = pd.to_datetime(fat["InvoiceDate"], errors="coerce")
    fat["InvoiceDate_Date"] = fat["InvoiceDate"].dt.normalize()
    fat["InvoiceDate_Time"] = fat["InvoiceDate"].dt.strftime("%H:%M:%S.%f").str.rstrip("0").str.rstrip(".")
    fat = fat.sort_values(["InvoiceDate_Date","InvoiceDate_Time"], kind="mergesort").reset_index(drop=True)
    return fat

def carregar_valores_conta(dir_root: Path) -> pd.DataFrame:
    files = _listar_ficheiros(dir_root)
    frames=[]
    for f in files:
        try:
            if f.suffix.lower() in (".xlsx",".xls"):
                try:
                    xls = pd.ExcelFile(f)
                    if "Valores_da_Conta" in xls.sheet_names:
                        dfv = pd.read_excel(f, sheet_name="Valores_da_Conta")
                        c_dt = encontrar_coluna(dfv, ["Data","Date","Booking date","Processed date","Transaction date","Posting date"])
                        c_vl = encontrar_coluna(dfv, ["Valor","Amount","Value","EUR","Total","Credit/Debit","Balance change"])
                        d = pd.DataFrame({
                            "Data": pd.to_datetime(dfv[c_dt], errors="coerce").dt.normalize(),
                            "Valor": normalize_amount_series(to_num_pt(dfv[c_vl]))
                        })
                        d = d.dropna(subset=["Data"])
                        frames.append(d)
                        continue
                except Exception:
                    pass
            raw = ler_qualquer_tabela(f)
        except Exception:
            continue

        c_dt = encontrar_coluna(raw, ["Data","Date","Booking date","Processed date","Transaction date","Posting date"])
        c_vl = encontrar_coluna(raw, ["Valor","Amount","Value","EUR","Total","Balance change"])
        c_cr = encontrar_coluna(raw, ["Credit","Crédito","Credit amount","CreditAmount"])
        c_db = encontrar_coluna(raw, ["Debit","Débito","Debit amount","DebitAmount"])

        if not c_dt:
            continue

        d_date = pd.to_datetime(raw[c_dt], errors="coerce").dt.normalize()

        if c_vl:
            v = normalize_amount_series(to_num_pt(raw[c_vl]))
        elif c_cr or c_db:
            cr = normalize_amount_series(to_num_pt(raw[c_cr])) if c_cr else 0.0
            db = normalize_amount_series(to_num_pt(raw[c_db])) if c_db else 0.0
            v = pd.Series(cr, dtype=float) - pd.Series(db, dtype=float)
        else:
            continue

        d = pd.DataFrame({"Data": d_date, "Valor": pd.to_numeric(v, errors="coerce").fillna(0.0)})
        d = d.dropna(subset=["Data"])
        frames.append(d)

    if not frames:
        return pd.DataFrame(columns=["Data","Valor"])

    df = pd.concat(frames, ignore_index=True)
    df = df.groupby("Data", as_index=False)["Valor"].sum()
    return df

# Indicadores base
def s_transactions_receita(trans: pd.DataFrame, tarifas: pd.DataFrame, idx=None) -> pd.Series:
    if idx is None: idx = IDX_DIAS
    if trans.empty: return pd.Series(0.0, index=idx)
    g = (trans.groupby(["Line","Intervalo","Vehicle"], as_index=False)
               .agg(Total=("CardPan","nunique")))
    g = g.merge(tarifas, on="Line", how="left")
    g["Receita"] = g["Tarifa"] * g["Total"]
    g["Data"] = pd.to_datetime(g["Intervalo"]).dt.normalize()
    s = g.groupby("Data")["Receita"].sum()
    return s.reindex(idx, fill_value=0.0)

def _serie_por_dia_from_excel(path_xlsx: Path, sheet: str, col_date: str, col_value: str, idx_datas) -> pd.Series:
    if not path_xlsx.exists():
        return pd.Series(0.0, index=idx_datas)
    df = pd.read_excel(path_xlsx, sheet_name=sheet)
    if df.empty:
        return pd.Series(0.0, index=idx_datas)
    if col_date not in df.columns or col_value not in df.columns:
        c_date = col_date if col_date in df.columns else encontrar_coluna(df, [col_date, "date", "data"])
        c_val  = col_value if col_value in df.columns else encontrar_coluna(df, [col_value, "amount", "valor", "price"])
        if not c_date or not c_val:
            return pd.Series(0.0, index=idx_datas)
        col_date, col_value = c_date, c_val

    df[col_date]  = pd.to_datetime(df[col_date], errors="coerce").dt.normalize()
    df[col_value] = pd.to_numeric(df[col_value], errors="coerce")

    if "Card Token" in df.columns:
        df = df.drop_duplicates(subset=[col_date, "Card Token", col_value], keep="last")
    else:
        df = df.drop_duplicates(subset=[col_date, col_value], keep="last")

    s = (df.dropna(subset=[col_date])
           .groupby(col_date)[col_value]
           .sum())
    return s.reindex(idx_datas, fill_value=0.0)

def _datas_do_quadro_existente(path_qs: Path) -> pd.DatetimeIndex | None:
    try:
        if not path_qs.exists():
            return None
        resumo = pd.read_excel(path_qs, sheet_name="Resumo")
        dias_row = resumo.loc[resumo["Indicador"] == "Dia"]
        if dias_row.empty:
            return None
        datas_str = list(dias_row.iloc[0, 1:])
        datas = pd.to_datetime(datas_str, format="%d/%m/%Y", errors="coerce")
        datas = datas.dropna().dt.normalize().unique()
        if len(datas) == 0:
            return None
        return pd.DatetimeIndex(sorted(datas))
    except Exception:
        return None

# Regras de comparação
def _serie_charges_para_recon(s_ch: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    vals = []
    for d in idx:
        if d.weekday() == 0:
            janela = [d - pd.Timedelta(days=3), d - pd.Timedelta(days=2), d - pd.Timedelta(days=1)]
        else:
            janela = [d - pd.Timedelta(days=1)]
        vals.append(float(s_ch.reindex(janela, fill_value=0.0).sum()))
    return pd.Series(vals, index=idx)

def _serie_recon_ref_para_conta(s_recon_payout: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    vals=[]
    for d in idx:
        if d.weekday() >= 5:
            vals.append(np.nan)
            continue
        if d == pd.Timestamp("2025-07-29"):
            v = float(s_recon_payout.get(pd.Timestamp("2025-07-25"), 0.0)) + \
                float(s_recon_payout.get(pd.Timestamp("2025-07-28"), 0.0))
            vals.append(v)
            continue
        if d.weekday() == 0:
            ref = d - pd.Timedelta(days=7)
        else:
            ref = d - pd.Timedelta(days=1)
        vals.append(float(s_recon_payout.get(ref, 0.0)))
    return pd.Series(vals, index=idx)

def _mask_weekends(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    m = s.copy().astype(float)
    for d in idx:
        if d.weekday() >= 5:
            m.loc[d] = np.nan
    return m

def _mask_where_zero(s: pd.Series, cond_series: pd.Series) -> pd.Series:
    out = s.copy().astype(float)
    out[cond_series.fillna(0.0) == 0.0] = np.nan
    return out

# (1) Analise_Transactions_09.xlsx
def gerar_analise_09():
    trans   = carregar_transactions(DIR_TRANS_ALL)
    ch      = carregar_charges(DIR_CHARGES_ALL)
    tarifas = carregar_tarifas(F_TARIFAS)

    g = (trans.groupby(["Line","Intervalo","Vehicle"], as_index=False)
               .agg(Total=("CardPan","nunique"),
                    Data=("Ts","min")))
    g = g.merge(tarifas, on="Line", how="left")
    g["Receita"] = g["Tarifa"] * g["Total"]

    analise = (g[["Line","Data","Intervalo","Vehicle","Total","Receita","Tarifa"]]
               .sort_values(["Line","Intervalo","Vehicle"], kind="mergesort"))

    alvo = {"nok - charge not successful","charge not attempted"}
    ch_ok = ch[ch["Charge status"].str.lower().eq("ok - charge collected")].copy()
    ch_ok["Date"] = pd.to_datetime(ch_ok["Date"]).dt.normalize()
    ch_ok["Fare charge amount"] = ch_ok["_Fare_num_eur"]
    tabela_cobrancas = (ch_ok[["Card Token","Card Scheme","Charge status","Date","Fare charge amount"]]
                        .drop_duplicates()
                        .sort_values(["Date","Card Token"], kind="mergesort"))

    rec = ch[ch["Charge status"].str.lower().isin(alvo) &
             ch["Debt status"].str.lower().eq("ok - recovered debt")].copy()
    rec["Debt recovered Date"] = pd.to_datetime(rec["Debt recovered date"]).dt.normalize()
    rec["Debt amount"] = rec["_Debt_num_eur"]
    tabela_rec = (rec[["Card Token","Card Scheme","Charge status","Debt status","Debt amount","Debt recovered Date"]]
                  .drop_duplicates()
                  .sort_values(["Debt recovered Date","Card Token"], kind="mergesort"))

    nr = ch[ch["Charge status"].str.lower().isin(alvo) &
            ch["Debt status"].str.lower().eq("nok - pending debt") &
            ch["Debt recovered date"].isna()].copy()
    nr["Debt created Date"] = pd.to_datetime(nr["Debt created date"]).dt.normalize()
    nr["Debt recovered Date"] = pd.NaT
    nr["Debt amount"] = nr["_Debt_num_eur"]
    tabela_nr = (nr[["Card Token","Card Scheme","Charge status","Debt status",
                     "Debt recovered Date","Debt amount","Debt created Date"]]
                 .drop_duplicates()
                 .sort_values(["Debt created Date","Card Token"], kind="mergesort"))

    hoje = pd.Timestamp(datetime.today().date())
    pend = ch[ch["Charge status"].str.lower().isin(alvo) &
              ch["Debt status"].str.lower().eq("nok - pending debt")].copy()
    pend["_Debt_created_dt"] = pd.to_datetime(pend["Debt created date"]).dt.normalize()
    pend["dias"] = (hoje - pend["_Debt_created_dt"]).dt.days
    scheme = pend["Card Scheme"].str.lower().fillna("")
    pend["prazo"] = np.where(
        scheme.str.contains("visa", case=False), 14,
        np.where(scheme.str.contains("mastercard|maestro", case=False, regex=True), 45, np.nan)
    )
    poss = pend[pend["dias"] <= pend["prazo"]].copy()
    poss["Debt created Date"] = pd.to_datetime(poss["Debt created date"]).dt.normalize()
    poss["Debt amount"] = poss["_Debt_num_eur"]
    poss["Date"] = pd.to_datetime(poss["Date"], errors="coerce").dt.normalize()
    poss.loc[poss["Date"].isna(), "Date"] = poss["Debt created Date"]
    cobrancas_poss = (poss[["Date","Card Token","Card Scheme","Debt created Date","dias","Debt amount"]]
                      .drop_duplicates()
                      .sort_values(["Debt created Date","Card Token"], kind="mergesort"))

    preju = pend[pend["dias"] > pend["prazo"]].copy()
    preju["Debt created Date"] = pd.to_datetime(preju["Debt created date"]).dt.normalize()
    preju["Debt amount"] = preju["_Debt_num_eur"]
    tabela_preju = (preju[["Card Token","Card Scheme","Debt created Date","dias","Debt amount"]]
                    .drop_duplicates()
                    .sort_values(["Debt created Date","Card Token"], kind="mergesort"))

    F_OUT_09.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(F_OUT_09, engine="xlsxwriter",
                        datetime_format="dd/mm/yyyy hh:mm:ss") as wr:
        wb  = wr.book
        fmt_date   = wb.add_format({"num_format": "dd/mm/yyyy hh:mm:ss"})
        fmt_dt_30s = wb.add_format({"num_format": "dd/mm/yyyy hh:mm:ss"})
        money      = wb.add_format({"num_format": "#,##0.00"})
        bold       = wb.add_format({"bold": True})

        analise.to_excel(wr, sheet_name="Análise_Transactions", index=False)
        sh = wr.sheets["Análise_Transactions"]
        sh.set_row(0, None, bold)
        sh.set_column(0, 0, 12)
        sh.set_column(1, 1, 20, fmt_date)
        sh.set_column(2, 2, 20, fmt_dt_30s)
        sh.set_column(3, 3, 12)
        sh.set_column(4, 4, 10)
        sh.set_column(5, 6, 14, money)

        tabela_cobrancas.to_excel(wr, sheet_name="Tabela_de_Cobranças", index=False)
        wr.sheets["Tabela_de_Cobranças"].set_row(0, None, bold)

        tabela_rec.to_excel(wr, sheet_name="Tabela_Recuperação_Dívidas", index=False)
        wr.sheets["Tabela_Recuperação_Dívidas"].set_row(0, None, bold)

        tabela_nr.to_excel(wr, sheet_name="Tabela_Cobranças_Não_Realizadas", index=False)
        wr.sheets["Tabela_Cobranças_Não_Realizadas"].set_row(0, None, bold)

        cobrancas_poss.to_excel(wr, sheet_name="Cobranças_possíveis_realizar", index=False)
        wr.sheets["Cobranças_possíveis_realizar"].set_row(0, None, bold)

        tabela_preju.to_excel(wr, sheet_name="Prejuízo", index=False)
        wr.sheets["Prejuízo"].set_row(0, None, bold)

    print(f"✅ Criado: {F_OUT_09}")

# (2) Quadro_Sintese_09.xlsx
def gerar_quadro_sintese():
    idx_existente = _datas_do_quadro_existente(F_OUT_SUM)
    idx = idx_existente if idx_existente is not None else IDX_DIAS

    # --- Séries base ---
    trans   = carregar_transactions(DIR_TRANS_ALL)
    tarifas = carregar_tarifas(F_TARIFAS)
    s_trans = s_transactions_receita(trans, tarifas, idx=idx)

    s_ch   = _serie_por_dia_from_excel(F_OUT_09, "Tabela_de_Cobranças",         "Date",               "Fare charge amount", idx)
    s_rec  = _serie_por_dia_from_excel(F_OUT_09, "Tabela_Recuperação_Dívidas",  "Debt recovered Date","Debt amount",        idx)
    s_prej = _serie_por_dia_from_excel(F_OUT_09, "Prejuízo",                     "Debt created Date",  "Debt amount",        idx)
    s_poss = _serie_por_dia_from_excel(F_OUT_09, "Cobranças_possíveis_realizar", "Date",               "Debt amount",        idx)

    recon  = carregar_reconciliation(DIR_RECON)
    conta  = carregar_valores_conta(DIR_CONTA)
    fat    = carregar_faturas(DIR_FATURAS)

    s_recon_payout = series_by_date(recon, "Payout Date", "Payout Amount", idx)
    s_recon_gross  = series_by_date(recon, "Payout Date", "Transaction Gross Amount", idx)
    s_conta        = series_by_date(conta, "Data", "Valor", idx)
    s_fat          = series_by_date(fat, "InvoiceDate_Date", "GrossTotal", idx)

    s_total = (s_ch + s_rec).fillna(0.0)

    # --- Tabela "Resumo" ---
    cols_datas = [d.strftime("%d/%m/%Y") for d in idx]
    rows = []
    rows.append(["Dia da Semana"] + [d.strftime("%A").capitalize() for d in idx])
    rows.append(["Dia"] + cols_datas)
    def r(nome, serie): return [nome] + list(np.round(serie.values, 2))
    rows.append(r("Transactions €", s_trans))
    rows.append(r("Charges €", s_ch))
    rows.append(r("Recuperação de Dívidas €", s_rec))
    rows.append(r("Total de Charges €", s_total))
    rows.append(r("Dívida Possível de Recuperar €", s_poss))
    rows.append(r("Reconciliation € PAYOUT_AMOUNT", s_recon_payout))
    rows.append(r("Reconciliation € TRANSACTION_GROSS_AMOUNT", s_recon_gross))
    rows.append(r("Valores da Conta €", s_conta))
    rows.append(r("Faturas €", s_fat))
    rows.append(r("Prejuízo €", s_prej))
    resumo_df = pd.DataFrame(rows, columns=["Indicador"] + cols_datas)

    # --- Cálculos para Comparação (mantidos, mas os valores não serão escritos) ---
    comp_trans_ch    = (s_trans - s_ch)
    s_ch_for_recon   = _serie_charges_para_recon(s_ch, idx)
    comp_ch_recon    = _mask_weekends(s_ch_for_recon - s_recon_gross, idx)
    s_recon_ref      = _serie_recon_ref_para_conta(s_recon_payout, idx)
    comp_recon_conta = s_recon_ref - s_conta
    comp_ch_fat_raw  = s_ch - s_fat
    comp_ch_fat      = _mask_where_zero(comp_ch_fat_raw, s_fat)
    comp_conta_fat   = s_conta - s_fat

    comp_rows = []
    comp_rows.append(["Transactions/Charges"]             + list(np.round(comp_trans_ch.values,    2)))
    comp_rows.append(["Charges/Reconciliation"]           + list(np.round(comp_ch_recon.values,     2)))
    comp_rows.append(["Reconciliation/ Conta"]            + list(np.round(comp_recon_conta.values,  2)))
    comp_rows.append(["Charges / Faturas"]                + list(np.round(comp_ch_fat.values,       2)))
    comp_rows.append(["Valores da Conta/ Faturas"]        + list(np.round(comp_conta_fat.values,    2)))
    comparacao_df = pd.DataFrame(comp_rows, columns=["Indicador"] + cols_datas)

    # >>> Deixar só os nomes dos indicadores; valores em branco
    comparacao_df_blank = comparacao_df.copy()
    for c in comparacao_df_blank.columns[1:]:
        comparacao_df_blank[c] = ""

    # --- Escrita em Excel ---
    F_OUT_SUM.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(F_OUT_SUM, engine="xlsxwriter", datetime_format="dd/mm/yyyy") as wr:
        wsname = "Resumo"
        resumo_df.to_excel(wr, sheet_name=wsname, startrow=0, startcol=0, index=False, header=True)

        # Linha em branco + título da secção
        startrow = len(resumo_df) + 3
        sht = wr.sheets[wsname]
        wb  = wr.book

        # Formatações
        money         = wb.add_format({"num_format":"#,##0.00"})
        bold          = wb.add_format({"bold": True})
        weekend_money = wb.add_format({"num_format":"#,##0.00", "bg_color":"#D9D9D9"})  # cinzento claro
        weekend_plain = wb.add_format({"bg_color":"#D9D9D9"})                           # sem formato numérico

        # Cabeçalho em negrito
        sht.set_row(0, None, bold)

        # Título da secção
        sht.write(startrow-1, 0, "Comparação de Valores", bold)

        # Escreve a tabela de comparação com valores em branco
        comparacao_df_blank.to_excel(wr, sheet_name=wsname, startrow=startrow, startcol=0, index=False, header=True)

        # Larguras e formato numérico por defeito
        last_col = 1 + len(cols_datas)
        sht.set_column(0, 0, 36)               # coluna "Indicador"
        sht.set_column(1, last_col, 12, money) # colunas de datas (formato monetário por defeito)

        # >>> Cinzento claro apenas até à última linha escrita
        # Altura total escrita: linhas do Resumo + linha em branco + título + cabeçalho da comparação + linhas da comparação
        comp_rows_cnt       = len(comparacao_df_blank)
        last_written_row    = startrow + 1 + comp_rows_cnt  # última linha com dados (0-based já compensado abaixo)

        weekend_cols = [1 + i for i, d in enumerate(idx) if d.weekday() >= 5]  # 1 = primeira coluna de datas

        for c in weekend_cols:
            # Pintar células COM conteúdo nesse intervalo
            sht.conditional_format(0, c, last_written_row, c, {
                "type": "no_blanks", "format": weekend_money
            })
            # Pintar células EM BRANCO nesse mesmo intervalo (para abranger as células vazias da comparação)
            sht.conditional_format(0, c, last_written_row, c, {
                "type": "blanks", "format": weekend_plain
            })

    print(f"✅ Criado: {F_OUT_SUM}")

# MAIN
def main():
    gerar_analise_09()
    gerar_quadro_sintese()

if __name__ == "__main__":
    main()










































































































# Análise para saber quantas transactions são "Operator" = Carris "Metropolitana"
# from pathlib import Path
# import pandas as pd
# import numpy as np

# DIR_TRANS = Path(r"C:\Users\MargaridaDias\TML\Gestão de Contratos - Documents\General\ISO\Projetos\CUT\Transactions")

# def ler_qualquer_tabela(f):
#     s = f.suffix.lower()
#     if s in (".csv", ".txt"):
#         return pd.read_csv(f, sep=None, engine="python")
#     if s in (".xlsx", ".xls"):
#         return pd.read_excel(f)
#     raise ValueError(f"Formato não suportado: {f.name}")

# def encontrar_coluna(df, candidatos):
#     m = {c.lower(): c for c in df.columns}
#     for padrao in candidatos:
#         p = padrao.lower()
#         for k, v in m.items():
#             if p in k:
#                 return v
#     return None

# def escolher_coluna_operator(df):
#     # 1) Preferir nome textual do operador
#     for pat in ["operator name", "operatorname", "operator", "operador"]:
#         c = encontrar_coluna(df, [pat])
#         if c: return c
#     # 2) Se não houver, cair para IDs
#     for pat in ["operator long id", "operatorlongid", "operator id", "operatorid"]:
#         c = encontrar_coluna(df, [pat])
#         if c: return c
#     return None

# def normalizar_operator(serie: pd.Series) -> pd.Series:
#     """
#     Converte para 'string' preservando NA, remove sufixos '.0' e espaços.
#     Se for numérica (int/float), converte inteiros para string sem '.0'.
#     """
#     s = serie.copy()

#     # Se for numérica, converter para Int64 (quando possível) e depois para string
#     if pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s):
#         # tenta converter para inteiro quando for valor inteiro (e preserva NA)
#         s_num = pd.to_numeric(s, errors="coerce")
#         s_int = s_num.where(s_num.isna() | (np.mod(s_num, 1) != 0), s_num.astype("Int64"))
#         # para os que não ficaram inteiros (raro), mantém como string normal
#         s = s_int.astype("string")
#         mask_nonint = s.isna() & s_num.notna()
#         if mask_nonint.any():
#             s = s.astype("object")
#             s[mask_nonint] = s_num[mask_nonint].astype(str)
#             s = s.astype("string")
#     else:
#         s = s.astype("string")

#     # limpeza de espaços e sufixos ".0"
#     s = s.str.strip()
#     s = s.str.replace(r"\.0+$", "", regex=True)

#     return s  # dtype 'string' com <NA> para ausentes

# # === Leitura & agregação ===
# files = [f for f in DIR_TRANS.glob("*") if f.suffix.lower() in (".csv", ".txt", ".xlsx", ".xls")]
# if not files:
#     raise FileNotFoundError(f"Nenhum ficheiro encontrado em {DIR_TRANS}")

# frames = []
# for f in files:
#     df = ler_qualquer_tabela(f)
#     c_op = escolher_coluna_operator(df)
#     if not c_op:
#         continue
#     op = normalizar_operator(df[c_op])
#     frames.append(pd.DataFrame({"Operator": op}))

# if not frames:
#     raise KeyError("Não encontrei coluna de operador ('Operator' / 'Operator ID' / 'OperatorLongId') em nenhum ficheiro.")

# df_all = pd.concat(frames, ignore_index=True)

# # === Métricas ===
# total_trans = int(df_all["Operator"].shape[0])
# is_CM = df_all["Operator"].str.lower().str.strip().eq("carris metropolitana")
# n_CM = int(is_CM.sum())
# pct_CM = (n_CM / total_trans) * 100 if total_trans else 0.0

# print(f"Total de transações lidas: {total_trans:,}")
# print(f"Transações 'Carris Metropolitana': {n_CM:,} ({pct_CM:.2f}%)")

# # === Distribuição por operador (exclui ausentes) ===
# distrib = (
#     df_all.loc[~df_all["Operator"].isna(), "Operator"]
#           .value_counts()
#           .reset_index()
#           .rename(columns={"index": "Operator", "Operator": "Num_Transacoes"})
# )

# print("\nDistribuição por operador (top 15):")
# print(distrib.head(15).to_string(index=False))