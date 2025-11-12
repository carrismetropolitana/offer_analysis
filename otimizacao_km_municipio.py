r"""
GTFS -> Repartição de km e nº de paragens por município (A1..A4 agregadas)

Ficheiro 1 (principal) — 5 folhas globais:
  - extension_per_municipality
  - paragens_pro municipio
  - indice_50_50
  - indice_50_50_x_veic_km
  - vkm_p_município  (Σ global do Valor_50_50_x_veic_km por concelho + coluna "Valor de referência do contrato")

Ficheiro 2 (REDIST) — MESMAS 5 folhas:
  - extension_per_municipality           (extensão redistribuída: extensão em concelhos sem paragens é redistribuída
                                          pelos concelhos com paragens, proporcional ao nº de paragens do pattern.
                                          Inclui coluna 'redistribuicao' = 'Sim'/'Não' e remove linhas a 0 nos casos 'Sim')
  - paragens_pro municipio               (igual ao ficheiro principal)
  - indice_50_50                         (recalculado com a extension_% redistribuída)
  - indice_50_50_x_veic_km               (recalculado)
  - vkm_p_município                      (recalculado + referência contratual)
"""

import re
import os
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime
import unicodedata

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

RAW_BASE = "https://raw.githubusercontent.com/marianadscosta/offer_analysis/main/inputs"

try:
    import requests
except ImportError:
    requests = None

def log(msg: str) -> None:
    print(msg, flush=True)

def _download_bytes(url: str, timeout: int = 30) -> bytes:
    try:
        if requests is not None:
            r = requests.get(url, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            return r.content
        else:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
    except (HTTPError, URLError, Exception) as e:
        raise RuntimeError(str(e)) from e

def _fetch_shapefile_to_temp(basename: str) -> str:
    required_exts = [".shp", ".shx", ".dbf"]
    optional_exts = [".prj", ".cpg"]
    tmpdir = tempfile.mkdtemp(prefix=f"tmp_{basename}_")
    for ext in required_exts:
        url = f"{RAW_BASE}/{basename}{ext}"
        data = _download_bytes(url)
        with open(os.path.join(tmpdir, f"{basename}{ext}"), "wb") as f:
            f.write(data)
    for ext in optional_exts:
        url = f"{RAW_BASE}/{basename}{ext}"
        try:
            data = _download_bytes(url)
            with open(os.path.join(tmpdir, f"{basename}{ext}"), "wb") as f:
                f.write(data)
        except Exception:
            pass
    return os.path.join(tmpdir, f"{basename}.shp")

def _norm_txt(s: str) -> str:
    s = str(s).strip().lower().replace("_", " ")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s)
    return s

# Parâmetros
BASE = Path(r"C:\Users\MargaridaDias\TML\Gestão de Contratos - Documents\General\ISO\1 Análise de Planos")
AREAS = [f"Área {i}" for i in (1, 2, 3, 4)]

OUT_BASE_DIR = Path(
    r"C:\Users\MargaridaDias\TML\Gestão de Contratos - Documents\General\Gestão contratual\Análises de Dados\02_2024\Repartição km"
)
OUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

DATE_TAG = datetime.now().strftime("%Y%m%d")
OUT_DAY_DIR = OUT_BASE_DIR / DATE_TAG
OUT_DAY_DIR.mkdir(parents=True, exist_ok=True)

# Ficheiro 1 (principal, 5 folhas)
OUT_SINGLE_PATH  = OUT_DAY_DIR / f"{DATE_TAG}_reparticao km_por município.xlsx"
# Ficheiro 2 (redistribuição, 5 folhas)
OUT_REDIST_PATH  = OUT_DAY_DIR / f"{DATE_TAG}_reparticao km_por município_REDIST.xlsx"

# Diretório do ficheiro de referência “20250328_Evolução km por municipio.xlsx”
REF_DIR = OUT_BASE_DIR

# Descoberta GTFS/comparador
def parse_year_month_from_name(name: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"(20\d{2})[-_ ]?(\d{2})", name)
    return (int(m.group(1)), int(m.group(2))) if m else None

def latest_month_folder_by_name(area_dir: Path) -> Optional[Path]:
    month_dirs = [d for d in area_dir.iterdir() if d.is_dir()]
    if not month_dirs:
        return None
    keyed = [(parse_year_month_from_name(d.name), d) for d in month_dirs]
    keyed = [(k, d) for (k, d) in keyed if k is not None]
    if keyed:
        keyed.sort(key=lambda x: (x[0][0], x[0][1]))
        return keyed[-1][1]
    return max(month_dirs, key=lambda p: p.stat().st_mtime)

def unzip_to(zip_path: Path, target_dir: Path) -> Path:
    if not target_dir.exists():
        log(f"  • A descomprimir: {zip_path.name}")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)
    return target_dir

def find_gtfs_candidate(month_dir: Path, force_ref: bool = False) -> Optional[Path]:
    cands = []
    for p in month_dir.iterdir():
        name_up = p.name.upper()
        if p.is_dir() and ("YEAR" in name_up or "REF" in name_up):
            tag = "YEAR" if "YEAR" in name_up else "REF"
            cands.append((tag, p, False))
        elif p.suffix.lower() == ".zip" and ("YEAR" in name_up or "REF" in name_up):
            tag = "YEAR" if "YEAR" in name_up else "REF"
            cands.append((tag, p, True))
    if not cands:
        return None
    tag_order = ["REF", "YEAR"] if force_ref else ["YEAR", "REF"]
    for tag in tag_order:
        tag_cands = [(path, is_zip) for (t, path, is_zip) in cands if t == tag]
        if not tag_cands:
            continue
        path, is_zip = sorted(tag_cands, key=lambda x: x[0].name)[-1]
        return unzip_to(path, month_dir / path.stem) if is_zip else path
    path, is_zip = sorted([(p, z) for (_, p, z) in cands], key=lambda x: x[0].name)[-1]
    return unzip_to(path, month_dir / path.stem) if is_zip else path

def find_latest_comparador_file(month_dir: Path, area_num: int) -> Optional[Path]:
    patt = re.compile(rf"^A{area_num}_analise_plano_anual_.*\.xlsx$", re.IGNORECASE)
    cands = [p for p in month_dir.iterdir() if p.is_file() and patt.match(p.name)]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)

# Leitura do comparador
def load_total_extension_from_comparador(xlsx_path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(xlsx_path)
    chosen_sheet = None
    for sh in xls.sheet_names:
        if "comparacao extensoes" in _norm_txt(sh):
            chosen_sheet = sh
            break
    if chosen_sheet is None:
        raise KeyError("Worksheet 'Comparação_extensões' (ou equivalente) não encontrada.")

    df = pd.read_excel(xls, sheet_name=chosen_sheet)

    key_col = None
    for c in df.columns:
        if _norm_txt(c) == "percurso":
            key_col = c
            break
    if key_col is None:
        for c in df.columns:
            if _norm_txt(c) in ("pattern_id", "pattern", "percurso id", "patternid"):
                key_col = c
                break
    if key_col is None:
        raise KeyError("Coluna 'Percurso' não encontrada em 'Comparação_extensões'.")

    total_col = None
    for c in df.columns:
        nc = _norm_txt(c)
        if "extensao" in nc and "shape" in nc and ("poperacao" in nc or "poper" in nc):
            total_col = c
            break
    if total_col is None:
        if "Extensão shape_POperação" in df.columns:
            total_col = "Extensão shape_POperação"
        else:
            raise KeyError("Coluna 'Extensão shape_POperação' não encontrada.")

    out = df[[key_col, total_col]].copy()
    out = out.rename(columns={key_col: "pattern_key", total_col: "total_extension_km"})
    out["pattern_key"] = out["pattern_key"].astype(str).str.strip()
    out["total_extension_km"] = (
        out["total_extension_km"].astype(str)
        .str.replace(",", ".").str.replace("\u00A0", "").str.strip()
    )
    out["total_extension_km"] = pd.to_numeric(out["total_extension_km"], errors="coerce")
    out = out.dropna(subset=["pattern_key", "total_extension_km"]).drop_duplicates(subset=["pattern_key"])
    return out

def load_veickm_from_comparador(xlsx_path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(xlsx_path)
    sheet = None
    for sh in xls.sheet_names:
        if "total circulacoes e vkm" in _norm_txt(sh):
            sheet = sh
            break
    if sheet is None:
        raise KeyError("Folha 'Total circulações e VKM' não encontrada.")

    df = pd.read_excel(xls, sheet_name=sheet)

    key_col = None
    for c in df.columns:
        if _norm_txt(c) == "percurso":
            key_col = c
            break
    if key_col is None:
        for c in df.columns:
            if _norm_txt(c) in ("pattern", "pattern id", "patternid", "percurso id"):
                key_col = c
                break
    if key_col is None:
        raise KeyError("Coluna 'Percurso' não encontrada na folha 'Total circulações e VKM'.")

    vkm_col = None
    for c in df.columns:
        nc = _norm_txt(c)
        if ("vkm" in nc) and ("total" in nc) and (("ano" in nc) or ("anual" in nc)) and (("poperacao" in nc) or ("poper" in nc)):
            vkm_col = c
            break
    if vkm_col is None:
        if "VKM total ano_POperação" in df.columns:
            vkm_col = "VKM total ano_POperação"
        else:
            raise KeyError("Coluna 'VKM total ano_POperação' não encontrada em 'Total circulações e VKM'.")

    use = df[[key_col, vkm_col]].copy()
    use = use.rename(columns={key_col: "pattern_key", vkm_col: "veic_km_total"})
    use["pattern_key"] = use["pattern_key"].astype(str).str.strip()
    use["veic_km_total"] = (
        use["veic_km_total"].astype(str)
        .str.replace(",", ".").str.replace("\u00A0", "").str.strip()
    )
    use["veic_km_total"] = pd.to_numeric(use["veic_km_total"], errors="coerce")
    out = use.groupby("pattern_key", as_index=False)["veic_km_total"].sum()
    out = out.dropna(subset=["pattern_key"])
    return out

def load_extension_by_municipio_from_comparador(xlsx_path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(xlsx_path)
    candidate_sheets = [sh for sh in xls.sheet_names if ("municip" in _norm_txt(sh)) or ("concelh" in _norm_txt(sh))]
    if not candidate_sheets:
        raise KeyError("Sem folha municipal no comparador.")
    chosen_sheet = candidate_sheets[-1]
    df = pd.read_excel(xls, sheet_name=chosen_sheet)

    key_col = None
    for c in df.columns:
        if _norm_txt(c) == "percurso":
            key_col = c
            break
    if key_col is None:
        for c in df.columns:
            if _norm_txt(c) in ("pattern_id", "pattern", "percurso id", "patternid"):
                key_col = c
                break
    if key_col is None:
        raise KeyError(f"A folha '{chosen_sheet}' não tem coluna 'Percurso' (ou equivalente).")

    df_num = df.copy()
    for c in df_num.columns:
        if c == key_col:
            continue
        df_num[c] = (
            df_num[c].astype(str)
            .str.replace(",", ".")
            .str.replace("\u00A0", "")
            .str.strip()
        )
        df_num[c] = pd.to_numeric(df_num[c], errors="coerce")

    muni_cols = [c for c in df_num.columns if c != key_col]
    muni_cols = [c for c in muni_cols if not re.search(r"\btotal\b", _norm_txt(c))]

    long_df = df_num.melt(
        id_vars=[key_col], value_vars=muni_cols,
        var_name="Concelho", value_name="km_raw"
    )
    long_df = long_df.rename(columns={key_col: "pattern_key"})
    long_df["pattern_key"] = long_df["pattern_key"].astype(str).str.strip()
    long_df["Concelho"] = long_df["Concelho"].astype(str).str.strip()
    long_df["km_raw"] = pd.to_numeric(long_df["km_raw"], errors="coerce").fillna(0.0)
    return long_df

# GTFS / shapefiles / paragens
def _ensure_pattern_id_in_trips(trips_df: pd.DataFrame) -> pd.DataFrame:
    if "pattern_id" not in trips_df.columns:
        trips_df = trips_df.copy()
        trips_df["pattern_id"] = trips_df["trip_id"].astype(str).str.split("_").str[:3].str.join("_")
        log("      (Aviso) 'pattern_id' não existia em trips — inferido de trip_id.")
    return trips_df

def build_shapefiles_from_gtfs_complete(gtfs_dir: Path, shp_dir: Path) -> None:
    log("    - A gerar shapefiles (versão COMPLETA)…")
    stops_df      = pd.read_csv(gtfs_dir / "stops.txt", dtype=str)
    stop_times_df = pd.read_csv(gtfs_dir / "stop_times.txt", dtype=str)
    shapes_df     = pd.read_csv(gtfs_dir / "shapes.txt", dtype=str)
    trips_df      = pd.read_csv(gtfs_dir / "trips.txt", dtype=str)
    routes_df     = pd.read_csv(gtfs_dir / "routes.txt", dtype=str) if (gtfs_dir / "routes.txt").exists() else pd.DataFrame()
    trips_df = _ensure_pattern_id_in_trips(trips_df)

    # stops
    for c in ("stop_lat", "stop_lon"):
        stops_df[c] = pd.to_numeric(stops_df[c], errors="coerce")
    stops_gdf = gpd.GeoDataFrame(stops_df, geometry=gpd.points_from_xy(stops_df.stop_lon, stops_df.stop_lat), crs="EPSG:4326")
    (shp_dir / "stops.shp").unlink(missing_ok=True)
    stops_gdf.to_file(shp_dir / "stops.shp")

    # stop_times
    st_merge = stop_times_df.merge(stops_df[["stop_id","stop_lon","stop_lat"]], on="stop_id", how="left")
    for c in ("stop_lat", "stop_lon"):
        st_merge[c] = pd.to_numeric(st_merge[c], errors="coerce")
    st_gdf = gpd.GeoDataFrame(st_merge, geometry=gpd.points_from_xy(st_merge.stop_lon, st_merge.stop_lat), crs="EPSG:4326")
    keep_trips = [c for c in ["trip_id","route_id","shape_id","pattern_id"] if c in trips_df.columns]
    if keep_trips:
        st_gdf = st_gdf.merge(trips_df[keep_trips], on="trip_id", how="left")
        if not routes_df.empty and "route_id" in routes_df.columns:
            keep_rt = [c for c in ["route_id","line_id","line_short_name","line_long_name",
                                   "route_origin","route_destination","route_short_name","route_long_name"]
                       if c in routes_df.columns]
            if keep_rt:
                st_gdf = st_gdf.merge(routes_df[keep_rt], on="route_id", how="left")
    (shp_dir / "stop_times.shp").unlink(missing_ok=True)
    st_gdf.to_file(shp_dir / "stop_times.shp")

    # shapes_points
    for c in ("shape_pt_lat","shape_pt_lon","shape_pt_sequence"):
        shapes_df[c] = pd.to_numeric(shapes_df[c], errors="coerce")
    shp_pts_gdf = gpd.GeoDataFrame(shapes_df, geometry=gpd.points_from_xy(shapes_df.shape_pt_lon, shapes_df.shape_pt_lat), crs="EPSG:4326")
    if "shape_id" in shp_pts_gdf.columns and "shape_id" in trips_df.columns:
        shp_pts_gdf = shp_pts_gdf.merge(
            trips_df.drop_duplicates(subset=["shape_id"])[["shape_id","pattern_id"]],
            on="shape_id", how="left"
        )
    (shp_dir / "shapes_points.shp").unlink(missing_ok=True)
    shp_pts_gdf.to_file(shp_dir / "shapes_points.shp")

    # shapes_lines
    def _to_lines(group: pd.DataFrame) -> Optional[LineString]:
        pts = group.sort_values("shape_pt_sequence")[["shape_pt_lon","shape_pt_lat"]].dropna().to_numpy()
        if len(pts) < 2:
            return None
        return LineString([(lon, lat) for lon, lat in pts])

    lines = (
        shapes_df.groupby("shape_id", as_index=False)
        .apply(lambda g: _to_lines(g))
        .rename(columns={None: "geometry"})
    )
    lines = lines.dropna(subset=["geometry"])
    lines_gdf = gpd.GeoDataFrame(lines, geometry="geometry", crs="EPSG:4326")

    if "shape_id" in trips_df.columns:
        map_df = trips_df.drop_duplicates(subset=["shape_id"])[["shape_id","pattern_id"]]
        lines_gdf = lines_gdf.merge(map_df, on="shape_id", how="left")

    (shp_dir / "shapes_lines.shp").unlink(missing_ok=True)
    lines_gdf.to_file(shp_dir / "shapes_lines.shp")

    # paragens_percursos
    par_perc = stop_times_df[["trip_id","stop_id","stop_sequence"]].merge(
        trips_df[["trip_id","pattern_id"]], on="trip_id", how="left"
    ).merge(
        stops_df[["stop_id","stop_lon","stop_lat"] + (["stop_name"] if "stop_name" in stops_df.columns else [])],
        on="stop_id", how="left"
    )
    for c in ("stop_lat","stop_lon"):
        par_perc[c] = pd.to_numeric(par_perc[c], errors="coerce")
    cols = ["pattern_id","stop_id","stop_sequence"] + (["stop_name"] if "stop_name" in stops_df.columns else [])
    par_gdf = gpd.GeoDataFrame(par_perc[cols], geometry=gpd.points_from_xy(par_perc.stop_lon, par_perc.stop_lat), crs="EPSG:4326")
    par_gdf = par_gdf.drop_duplicates(subset=["pattern_id","stop_id","stop_sequence"])
    (shp_dir / "paragens_percursos.shp").unlink(missing_ok=True)
    par_gdf.to_file(shp_dir / "paragens_percursos.shp")

def concelho_field_name(cols: List[str]) -> str:
    for c in ["Concelho", "concelho", "Municipio", "Município", "NAME_2", "NAME"]:
        if c in cols:
            return c
    raise KeyError("Campo do concelho não encontrado no Concelhos.shp.")

def _ensure_pattern_if_missing(
    gdf: gpd.GeoDataFrame, gtfs_dir: Path, key_cols: List[str]
) -> gpd.GeoDataFrame:
    if "pattern_id" in gdf.columns:
        return gdf
    trips = pd.read_csv(gtfs_dir / "trips.txt", dtype=str)
    if "pattern_id" not in trips.columns:
        trips["pattern_id"] = trips["trip_id"].astype(str).str.split("_").str[:3].str.join("_")
    gdf2 = gdf.copy()
    for key in key_cols:
        if key in gdf2.columns and key in trips.columns:
            map_df = trips[[key, "pattern_id"]].dropna().drop_duplicates(subset=[key])
            gdf2 = gdf2.merge(map_df, on=key, how="left")
            if gdf2["pattern_id"].notna().any():
                log(f"    [RECUP] 'pattern_id' reconstruído via {key} -> trips.txt")
                return gdf2
            gdf2 = gdf2.drop(columns=["pattern_id"], errors="ignore")
    raise KeyError("Não foi possível reconstruir 'pattern_id' a partir de trips.txt.")

# Reconciliação municipal
def reconcile_municipal_km(muni_df: pd.DataFrame, totals_df: pd.DataFrame) -> pd.DataFrame:
    df = muni_df.merge(totals_df, on="pattern_key", how="inner").copy()
    sums = df.groupby("pattern_key")["km_raw"].sum().rename("sum_raw")
    df = df.merge(sums, on="pattern_key", how="left")

    df["factor"] = df.apply(
        lambda r: (r["total_extension_km"] / r["sum_raw"]) if r["sum_raw"] and r["sum_raw"] > 0 else 0.0,
        axis=1
    )
    df["extension_km"] = df["km_raw"] * df["factor"]

    def _snap(group: pd.DataFrame) -> pd.DataFrame:
        total = group["total_extension_km"].iloc[0]
        diff = total - group["extension_km"].sum()
        if abs(diff) > 1e-9 and len(group) > 0:
            idx_max = group["extension_km"].idxmax()
            group.loc[idx_max, "extension_km"] = group.loc[idx_max, "extension_km"] + diff
        return group

    df = df.groupby("pattern_key", group_keys=False).apply(_snap)

    df["extension_%"] = df.apply(
        lambda r: (r["extension_km"] / r["total_extension_km"]) if r["total_extension_km"] else 0.0, axis=1
    )
    df["total_extension_%"] = 1.0

    out = df.rename(columns={"pattern_key": "pattern_id"})[
        ["pattern_id", "Concelho", "extension_km", "total_extension_km", "extension_%", "total_extension_%"]
    ]
    out["extension_km"] = out["extension_km"].round(6)
    out["extension_%"]  = out["extension_%"].round(8)
    return out

# Paragens: contagens + %
def construir_paragens_sheet(shp_dir: Path) -> pd.DataFrame:
    conc_shp_path = _fetch_shapefile_to_temp("Concelhos")
    par_perc  = gpd.read_file(shp_dir / "paragens_percursos.shp")
    conc      = gpd.read_file(conc_shp_path)

    gtfs_dir = shp_dir.parent
    if "pattern_id" not in par_perc.columns:
        par_perc = _ensure_pattern_if_missing(par_perc, gtfs_dir, key_cols=["trip_id", "shape_id"])

    st_int = gpd.sjoin(par_perc.to_crs(conc.crs), conc, how="inner", predicate="within")
    cname = concelho_field_name(st_int.columns.tolist())
    stops_count = st_int.groupby(["pattern_id", cname]).size().reset_index(name="stop_count")

    pivot_par = stops_count.pivot_table(
        index="pattern_id", columns=cname, values="stop_count", aggfunc="sum", fill_value=0
    )
    pivot_par["Grand Total"] = pivot_par.sum(axis=1)
    pivot_par = pivot_par.reset_index()
    concelhos = [c for c in pivot_par.columns if c not in ("pattern_id", "Grand Total")]
    for c in concelhos:
        pivot_par[f"{c} (%)"] = pivot_par.apply(
            lambda r: (r[c] / r["Grand Total"]) if r["Grand Total"] else 0.0, axis=1
        )
    pivot_par["Grand Total (%)"] = 1.0
    return pivot_par

# ===== CORREÇÃO: preservar 'Área' no índice 50/50 =====
def _construir_indice_50_50_generico(ext_df: pd.DataFrame, pivot_par_df: pd.DataFrame) -> pd.DataFrame:
    """
    Constrói o índice 50/50 preservando 'Área' se existir em ambos os DataFrames.
    Saída:
      - Sem 'Área' nas entradas:  ['pattern_id','Concelho','stops_%','extension_%','Indice_50_50']
      - Com 'Área' nas entradas:  ['Área','pattern_id','Concelho','stops_%','extension_%','Indice_50_50']
    """
    has_area = ("Área" in ext_df.columns) and ("Área" in pivot_par_df.columns)

    # 1) % de paragens (wide -> long)
    pct_cols = [c for c in pivot_par_df.columns if str(c).endswith("(%)") and str(c) != "Grand Total (%)"]
    id_vars_par = (["Área"] if has_area else []) + ["pattern_id"]
    long_stops = pivot_par_df[id_vars_par + pct_cols].melt(
        id_vars=id_vars_par,
        value_vars=pct_cols,
        var_name="Concelho",
        value_name="stops_%"
    ).copy()
    long_stops["Concelho"] = (
        long_stops["Concelho"]
        .str.replace(r"\s*\(%\)\s*$", "", regex=True)
        .str.strip()
    )
    long_stops["stops_%"] = pd.to_numeric(long_stops["stops_%"], errors="coerce").fillna(0.0)

    # 2) % de extensão
    use_cols_ext = (["Área"] if has_area else []) + ["pattern_id", "Concelho", "extension_%"]
    ext_pct = ext_df[use_cols_ext].copy()
    ext_pct["extension_%"] = pd.to_numeric(ext_pct["extension_%"], errors="coerce").fillna(0.0)

    # 3) Merge
    on_keys = (["Área"] if has_area else []) + ["pattern_id", "Concelho"]
    m = ext_pct.merge(long_stops, on=on_keys, how="outer")
    m["extension_%"] = m["extension_%"].fillna(0.0)
    m["stops_%"]     = m["stops_%"].fillna(0.0)

    # 4) Índice
    m["Indice_50_50"] = 0.5 * m["stops_%"] + 0.5 * m["extension_%"]

    # 5) Remover zeros completos
    eps = 1e-12
    m = m[(m["stops_%"].abs() > eps) | (m["extension_%"].abs() > eps)]

    sort_cols = (["Área"] if has_area else []) + ["pattern_id", "Concelho"]
    m = m.sort_values(sort_cols).reset_index(drop=True)
    out_cols = (["Área"] if has_area else []) + ["pattern_id", "Concelho", "stops_%", "extension_%", "Indice_50_50"]
    return m[out_cols]

def construir_indice_50_50(ext_df: pd.DataFrame, pivot_par_df: pd.DataFrame) -> pd.DataFrame:
    return _construir_indice_50_50_generico(ext_df, pivot_par_df)

def construir_indice_50_50_x_veickm(indice_df: pd.DataFrame, veickm_df: pd.DataFrame) -> pd.DataFrame:
    m = indice_df.merge(veickm_df, left_on="pattern_id", right_on="pattern_key", how="left")
    m = m.drop(columns=["pattern_key"], errors="ignore")
    m["veic_km_total"] = pd.to_numeric(m["veic_km_total"], errors="coerce").fillna(0.0)
    m["Valor_50_50_x_veic_km"] = m["Indice_50_50"] * m["veic_km_total"]
    m = m.sort_values(["pattern_id", "Concelho"]).reset_index(drop=True)
    return m[["Área", "pattern_id", "Concelho", "Indice_50_50", "veic_km_total", "Valor_50_50_x_veic_km"]] if "Área" in indice_df.columns else m[["pattern_id", "Concelho", "Indice_50_50", "veic_km_total", "Valor_50_50_x_veic_km"]]

# Referência contratual
def _find_ref_file(base_dir: Path) -> Optional[Path]:
    hits = []
    for p in base_dir.rglob("*"):
        if p.is_file():
            n = _norm_txt(p.name)
            if "20250328" in n and "km por municipio" in n and (p.suffix.lower() in (".xlsx", ".xls")):
                hits.append(p)
    return max(hits, key=lambda x: x.stat().st_mtime) if hits else None

def _read_ref_vkm_exact(path: Path) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=1)
    cols = list(df.columns)
    if len(cols) < 2:
        raise KeyError("Estrutura inesperada na referência (esperadas colunas A e B).")
    colA, colB = cols[0], cols[1]
    out = df[[colA, colB]].copy()
    out.columns = ["Concelho", "Valor de referência do contrato"]
    out = out[out["Concelho"].notna()]
    out = out[out["Concelho"].astype(str).str.strip().str.lower() != "municipio"]
    out["Concelho"] = out["Concelho"].astype(str).str.strip()
    out["Valor de referência do contrato"] = (
        out["Valor de referência do contrato"].astype(str).str.replace(",", ".").str.replace("\u00A0", "").str.strip()
    )
    out["Valor de referência do contrato"] = pd.to_numeric(out["Valor de referência do contrato"], errors="coerce")
    out = out.dropna(subset=["Concelho"])
    out["_key"] = out["Concelho"].map(_norm_txt)
    return out[["Concelho", "Valor de referência do contrato", "_key"]]

# Execução por área
def correr_reparticao(month_dir: Path, gtfs_dir: Path, area_num: int):
    comp_path = find_latest_comparador_file(month_dir, area_num)
    if not comp_path:
        raise FileNotFoundError("Nenhum 'A*_analise_plano_anual_*.xlsx' encontrado na pasta do mês.")
    log(f"    • Comparador detetado: {comp_path.name}")

    totais = load_total_extension_from_comparador(comp_path)
    try:
        veickm = load_veickm_from_comparador(comp_path)
        log("    • VKM total ano_POperação lido da folha 'Total circulações e VKM'.")
    except Exception as e:
        log(f"    • [Aviso] Não foi possível ler VKM do comparador ({e}). A usar fallback (Extensão shape_POperação).")
        veickm = totais.rename(columns={"total_extension_km": "veic_km_total"})

    try:
        muni = load_extension_by_municipio_from_comparador(comp_path)
        source = "comparador"
    except Exception as e:
        log(f"    • [Aviso] Sem folha municipal no comparador ({e}). Usar fallback geométrico.")
        conc_shp = _fetch_shapefile_to_temp("Concelhos")
        brg_shp  = _fetch_shapefile_to_temp("bridges")
        conc = gpd.read_file(conc_shp)
        brg  = gpd.read_file(brg_shp)
        lines = gpd.read_file(gtfs_dir / "shapefiles" / "shapes_lines.shp")
        if "pattern_id" not in lines.columns:
            lines = _ensure_pattern_if_missing(lines, gtfs_dir, key_cols=["shape_id", "trip_id"])
        lines_no_b = gpd.overlay(lines.to_crs(brg.crs), brg, how="difference")
        li_int = gpd.overlay(lines_no_b.to_crs(conc.crs), conc, how="intersection")
        proj = li_int.to_crs("EPSG:3857")
        li_int["km_raw"] = proj.geometry.length / 1000.0
        cname = concelho_field_name(li_int.columns.tolist())
        muni = (
            li_int.groupby(["pattern_id", cname])["km_raw"].sum().reset_index()
            .rename(columns={"pattern_id": "pattern_key", cname: "Concelho"})
        )
        source = "geométrico"

    ext_df = reconcile_municipal_km(muni, totais)
    log(f"    • Repartição municipal (fonte: {source}) reconciliada ao total oficial.")

    pivot_par = construir_paragens_sheet(gtfs_dir / "shapefiles")
    # acrescentar 'Área' antes do índice, para propagar
    ext_df = ext_df.copy(); ext_df.insert(0, "Área", f"A{area_num}")
    pivot_par = pivot_par.copy(); pivot_par.insert(0, "Área", f"A{area_num}")
    idx_50_50 = construir_indice_50_50(ext_df, pivot_par)
    idx_50_50_x_veic = construir_indice_50_50_x_veickm(idx_50_50, load_veickm_from_comparador(comp_path))

    return ext_df, pivot_par, idx_50_50, idx_50_50_x_veic

# === Redistribuição de extensão por Área × pattern ===
def _redistribuir_extensao(df_ext_area: pd.DataFrame, df_par_area: pd.DataFrame) -> pd.DataFrame:
    """
    Devolve extension_per_municipality REDISTRIBUÍDA com coluna 'redistribuicao' = 'Sim'/'Não'.
    Nos patterns redistribuídos, elimina linhas cuja extensão fique a 0.
    """
    base_cols = [c for c in df_par_area.columns if c not in ("Área", "pattern_id")]
    count_cols = [c for c in base_cols if not str(c).endswith("(%)") and str(c) != "Grand Total"]

    par_long = df_par_area[["Área", "pattern_id"] + count_cols].melt(
        id_vars=["Área", "pattern_id"],
        value_vars=count_cols,
        var_name="Concelho",
        value_name="stop_count"
    )
    par_long["stop_count"] = pd.to_numeric(par_long["stop_count"], errors="coerce").fillna(0).astype(float)

    m = df_ext_area.merge(par_long, on=["Área", "pattern_id", "Concelho"], how="left")
    m["stop_count"] = m["stop_count"].fillna(0.0)

    def _redistribui(gr: pd.DataFrame) -> pd.DataFrame:
        gr = gr.copy()
        donors_mask = (gr["stop_count"] == 0) & (gr["extension_km"] > 0)
        donor_sum = gr.loc[donors_mask, "extension_km"].sum()

        recipients_mask = gr["stop_count"] > 0
        w_sum = gr.loc[recipients_mask, "stop_count"].sum()

        gr["extension_km_red"] = gr["extension_km"]
        houve_redistrib = False

        if donor_sum > 0 and w_sum > 0:
            houve_redistrib = True
            gr.loc[donors_mask, "extension_km_red"] = 0.0
            gr.loc[recipients_mask, "extension_km_red"] = (
                gr.loc[recipients_mask, "extension_km"] +
                donor_sum * (gr.loc[recipients_mask, "stop_count"] / w_sum)
            )
            total = gr["total_extension_km"].iloc[0]
            diff = total - gr["extension_km_red"].sum()
            if abs(diff) > 1e-9:
                idx_max = gr["extension_km_red"].idxmax()
                gr.loc[idx_max, "extension_km_red"] += diff

        total = gr["total_extension_km"].iloc[0]
        gr["extension_%"] = gr["extension_km_red"] / total if total else 0.0
        gr["total_extension_%"] = 1.0
        gr["redistribuicao"] = "Sim" if houve_redistrib else "Não"

        # Remover linhas com extensão 0 quando houve redistribuição
        if houve_redistrib:
            gr = gr[gr["extension_km_red"] > 1e-12].copy()

        return gr

    red = m.groupby(["Área", "pattern_id"], group_keys=False).apply(_redistribui)

    out = red[[
        "Área", "pattern_id", "Concelho",
        "extension_km_red", "total_extension_km",
        "extension_%", "total_extension_%",
        "redistribuicao"
    ]].rename(columns={"extension_km_red": "extension_km"})

    out["extension_km"] = out["extension_km"].round(6)
    out["extension_%"]  = out["extension_%"].round(8)
    return out

# MAIN — agrega A1..A4 e escreve os dois ficheiros
def run_pipeline() -> None:
    all_ext = []
    all_par = []
    all_idx = []
    all_ixv = []

    ref_path = _find_ref_file(REF_DIR)
    ref_df = None
    if ref_path and ref_path.exists():
        log(f"\n• Ficheiro de referência detetado: {ref_path}")
        try:
            ref_df = _read_ref_vkm_exact(ref_path)
        except Exception as e:
            log(f"  [Aviso] Não foi possível ler a referência ({e}).")

    for area in AREAS:
        area_dir = BASE / area
        if not area_dir.exists():
            log(f"[Aviso] Pasta não encontrada: {area_dir}")
            continue

        log(f"\n=== {area} ===")
        month_dir = latest_month_folder_by_name(area_dir)
        if not month_dir:
            log("  • Sem pastas de mês — ignorado.")
            continue
        log(f"- Último mês detetado: {month_dir.name}")

        force_ref = "Área 4" in area
        gtfs_dir = find_gtfs_candidate(month_dir, force_ref=force_ref)
        if not gtfs_dir:
            log("  • GTFS YEAR/REF não encontrado — ignorado.")
            continue
        log(f"  • GTFS escolhido: {gtfs_dir.name}")

        shp_dir = gtfs_dir / "shapefiles"
        shp_dir.mkdir(exist_ok=True)
        try:
            build_shapefiles_from_gtfs_complete(gtfs_dir, shp_dir)
            log("    ✓ Shapefiles completos gerados.")
        except Exception as e:
            log(f"    [ERRO GTFS->SHP] {e}")
            continue

        try:
            area_num = int(re.search(r"Área\s*(\d+)", area).group(1))
            ext_df, pivot_par_df, indice_df, indice_x_veic_df = correr_reparticao(month_dir, gtfs_dir, area_num)

            all_ext.append(ext_df)
            all_par.append(pivot_par_df)
            all_idx.append(indice_df)
            all_ixv.append(indice_x_veic_df)

        except SystemExit:
            raise
        except FileNotFoundError as e:
            log(f"    [ERRO INPUT] {e}")
        except KeyError as e:
            log(f"    [ERRO] {e}")
        except Exception as e:
            log(f"    [ERRO] {e}")

    if not all_ext:
        log("\n[ERRO] Não há dados para escrever.")
        return

    # Concatenados GLOBAIS
    df_ext = pd.concat(all_ext, ignore_index=True, sort=False)
    df_par = pd.concat(all_par, ignore_index=True, sort=False)
    df_idx = pd.concat(all_idx, ignore_index=True, sort=False)
    df_ixv = pd.concat(all_ixv, ignore_index=True, sort=False)

    # 1) vkm_p_município (principal)
    df_vkm_mun = (
        df_ixv
        .assign(Valor_50_50_x_veic_km=lambda d: pd.to_numeric(d["Valor_50_50_x_veic_km"], errors="coerce").fillna(0.0))
        .groupby("Concelho", as_index=False)["Valor_50_50_x_veic_km"].sum()
        .rename(columns={"Valor_50_50_x_veic_km": "VKM_total"})
        .sort_values("Concelho")
    )
    if ref_df is not None:
        try:
            df_vkm_mun["_key"] = df_vkm_mun["Concelho"].map(_norm_txt)
            df_vkm_mun = (
                df_vkm_mun
                .merge(ref_df[["_key", "Valor de referência do contrato"]], on="_key", how="left")
                .drop(columns=["_key"])
            )
        except Exception as e:
            log(f"\n• [Aviso] Não foi possível juntar a referência (principal) ({e}).")

    # ===== Montagem do ficheiro PRINCIPAL =====
    with pd.ExcelWriter(
        OUT_SINGLE_PATH,
        engine="xlsxwriter",
        engine_kwargs={"options": {"strings_to_urls": False}}
    ) as xlw:
        pct_fmt = xlw.book.add_format({"num_format": "0.00%"})
        km_fmt  = xlw.book.add_format({"num_format": "0.000"})
        num_fmt = xlw.book.add_format({"num_format": "#,##0.000"})

        # 1) extension_per_municipality
        sh = "extension_per_municipality"
        cols1 = ["Área", "pattern_id", "Concelho", "extension_km", "total_extension_km", "extension_%", "total_extension_%"]
        df_ext[cols1].to_excel(xlw, index=False, sheet_name=sh)
        ws = xlw.sheets[sh]
        for i, c in enumerate(cols1):
            width = 16
            if c in ("extension_km", "total_extension_km"):
                ws.set_column(i, i, width, km_fmt)
            elif c.endswith("%"):
                ws.set_column(i, i, width, pct_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 2) paragens_pro municipio
        sh = "paragens_pro municipio"
        df_par.to_excel(xlw, index=False, sheet_name=sh)
        ws = xlw.sheets[sh]
        for col_idx, col in enumerate(df_par.columns):
            try:
                width = max(12, min(40, int(df_par[col].astype(str).str.len().max()) + 2))
            except Exception:
                width = 14
            if str(col).endswith("(%)"):
                ws.set_column(col_idx, col_idx, width, pct_fmt)
            else:
                ws.set_column(col_idx, col_idx, width)

        # 3) indice_50_50
        sh = "indice_50_50"
        cols3 = ["Área", "pattern_id", "Concelho", "stops_%", "extension_%", "Indice_50_50"]
        df_idx[cols3].to_excel(xlw, index=False, sheet_name=sh)
        ws = xlw.sheets[sh]
        for i, c in enumerate(cols3):
            width = 16
            if c in ("stops_%", "extension_%", "Indice_50_50"):
                ws.set_column(i, i, width, pct_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 4) indice_50_50_x_veic_km
        sh = "indice_50_50_x_veic_km"
        cols4 = ["Área", "pattern_id", "Concelho", "Indice_50_50", "veic_km_total", "Valor_50_50_x_veic_km"]
        df_ixv[cols4].to_excel(xlw, index=False, sheet_name=sh)
        ws = xlw.sheets[sh]
        for i, c in enumerate(cols4):
            width = 18
            if c in ("Indice_50_50",):
                ws.set_column(i, i, width, pct_fmt)
            elif c in ("veic_km_total", "Valor_50_50_x_veic_km"):
                ws.set_column(i, i, width, num_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 5) vkm_p_município
        sh = "vkm_p_município"
        cols5 = ["Concelho", "VKM_total"] + (["Valor de referência do contrato"] if "Valor de referência do contrato" in df_vkm_mun.columns else [])
        df_vkm_mun[cols5].to_excel(xlw, index=False, sheet_name=sh)
        ws = xlw.sheets[sh]
        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 18, num_fmt)
        if "Valor de referência do contrato" in df_vkm_mun.columns:
            ws.set_column(2, 2, 26, num_fmt)

    log(f"\n✓ Ficheiro principal (5 folhas) gerado: {OUT_SINGLE_PATH}")

    # Construção das folhas REDIST
    # 1) extension_per_municipality (redistribuída)
    df_ext_red = _redistribuir_extensao(df_ext, df_par)

    # 2) indice_50_50 (redistribuído)
    df_idx_red = _construir_indice_50_50_generico(df_ext_red, df_par)

    # 3) indice_50_50_x_veic_km (redistribuído)
    veic_por_pattern = (
        df_ixv[["Área", "pattern_id", "veic_km_total"]]
        .drop_duplicates()
    )
    df_idx_red_with_vkm = df_idx_red.merge(
        veic_por_pattern, on=["Área", "pattern_id"], how="left"
    )
    df_ixv_red = df_idx_red_with_vkm.copy()
    df_ixv_red["Valor_50_50_x_veic_km"] = df_ixv_red["Indice_50_50"] * pd.to_numeric(df_ixv_red["veic_km_total"], errors="coerce").fillna(0.0)
    df_ixv_red = df_ixv_red[["Área", "pattern_id", "Concelho", "Indice_50_50", "veic_km_total", "Valor_50_50_x_veic_km"]]

    # 4) vkm_p_município (redistribuído)
    df_vkm_mun_red = (
        df_ixv_red
        .assign(Valor_50_50_x_veic_km=lambda d: pd.to_numeric(d["Valor_50_50_x_veic_km"], errors="coerce").fillna(0.0))
        .groupby("Concelho", as_index=False)["Valor_50_50_x_veic_km"].sum()
        .rename(columns={"Valor_50_50_x_veic_km": "VKM_total"})
        .sort_values("Concelho")
    )
    if ref_df is not None:
        try:
            df_vkm_mun_red["_key"] = df_vkm_mun_red["Concelho"].map(_norm_txt)
            df_vkm_mun_red = (
                df_vkm_mun_red
                .merge(ref_df[["_key", "Valor de referência do contrato"]], on="_key", how="left")
                .drop(columns=["_key"])
            )
        except Exception as e:
            log(f"\n• [Aviso] Não foi possível juntar a referência (REDIST) ({e}).")

    # Montagem do ficheiro REDIST (5 folhas)
    with pd.ExcelWriter(
        OUT_REDIST_PATH,
        engine="xlsxwriter",
        engine_kwargs={"options": {"strings_to_urls": False}}
    ) as xlw2:
        pct_fmt = xlw2.book.add_format({"num_format": "0.00%"})
        km_fmt  = xlw2.book.add_format({"num_format": "0.000"})
        num_fmt = xlw2.book.add_format({"num_format": "#,##0.000"})

        # 1) extension_per_municipality (redistribuída)
        sh = "extension_per_municipality"
        cols1 = [
            "Área", "pattern_id", "Concelho",
            "extension_km", "total_extension_km",
            "extension_%", "total_extension_%",
            "redistribuicao"   # nova coluna
        ]
        df_ext_red[cols1].to_excel(xlw2, index=False, sheet_name=sh)
        ws = xlw2.sheets[sh]
        for i, c in enumerate(cols1):
            width = 18
            if c in ("extension_km", "total_extension_km"):
                ws.set_column(i, i, width, km_fmt)
            elif c.endswith("%"):
                ws.set_column(i, i, width, pct_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 2) paragens_pro municipio
        sh = "paragens_pro municipio"
        df_par.to_excel(xlw2, index=False, sheet_name=sh)
        ws = xlw2.sheets[sh]
        for col_idx, col in enumerate(df_par.columns):
            try:
                width = max(12, min(40, int(df_par[col].astype(str).str.len().max()) + 2))
            except Exception:
                width = 14
            if str(col).endswith("(%)"):
                ws.set_column(col_idx, col_idx, width, pct_fmt)
            else:
                ws.set_column(col_idx, col_idx, width)

        # 3) indice_50_50 (redistribuído)
        sh = "indice_50_50"
        cols3 = ["Área", "pattern_id", "Concelho", "stops_%", "extension_%", "Indice_50_50"]
        df_idx_red[cols3].to_excel(xlw2, index=False, sheet_name=sh)
        ws = xlw2.sheets[sh]
        for i, c in enumerate(cols3):
            width = 16
            if c in ("stops_%", "extension_%", "Indice_50_50"):
                ws.set_column(i, i, width, pct_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 4) indice_50_50_x_veic_km (redistribuído)
        sh = "indice_50_50_x_veic_km"
        cols4 = ["Área", "pattern_id", "Concelho", "Indice_50_50", "veic_km_total", "Valor_50_50_x_veic_km"]
        df_ixv_red[cols4].to_excel(xlw2, index=False, sheet_name=sh)
        ws = xlw2.sheets[sh]
        for i, c in enumerate(cols4):
            width = 18
            if c in ("Indice_50_50",):
                ws.set_column(i, i, width, pct_fmt)
            elif c in ("veic_km_total", "Valor_50_50_x_veic_km"):
                ws.set_column(i, i, width, num_fmt)
            else:
                ws.set_column(i, i, max(14, width))

        # 5) vkm_p_município (redistribuído)
        sh = "vkm_p_município"
        cols5 = ["Concelho", "VKM_total"] + (["Valor de referência do contrato"] if "Valor de referência do contrato" in df_vkm_mun_red.columns else [])
        df_vkm_mun_red[cols5].to_excel(xlw2, index=False, sheet_name=sh)
        ws = xlw2.sheets[sh]
        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 18, num_fmt)
        if "Valor de referência do contrato" in df_vkm_mun_red.columns:
            ws.set_column(2, 2, 26, num_fmt)

    log(f"✓ Ficheiro REDIST (5 folhas) gerado: {OUT_REDIST_PATH}")

if __name__ == "__main__":
    run_pipeline()