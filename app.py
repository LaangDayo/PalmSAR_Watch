"""
PalmSAR Watch — WebGIS dashboard styled to the NASA Space Apps Challenge Brand Guidelines
(updated June 25, 2026).

Expected data:
    data/<site_id>/stack.nc
    data/<site_id>/meta.json

Optional brand assets (download from spaceappschallenge.org/brand, do not redraw them):
    assets/space_apps_logo_horizontal.png   -> Default (horizontal) logo, white colorway, for the header
    assets/space_apps_logo_small.png        -> Small logo, used as the browser favicon

Run:
    streamlit run app_spaceapps.py
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import folium
import matplotlib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import xarray as xr
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PALMSAR_DATA_DIR", ROOT / "data"))
ASSETS = ROOT / "assets"
LOGO_DEFAULT = ASSETS / "space_apps_logo_horizontal.png"
LOGO_SMALL = ASSETS / "space_apps_logo_small.png"

# ------------------------- Brand palette (Guidelines p.7) -------------------
BLUE_YONDER = "#2E96F5"
NEON_BLUE = "#0960E1"
ROCKET_RED = "#E43700"
MARTIAN_RED = "#8E1100"
ELECTRIC_BLUE = "#0042A6"
NEON_YELLOW = "#EAFE07"
DEEP_BLUE = "#07173F"
WHITE = "#FFFFFF"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def eased_gradient_css(start: str, end: str, angle: int = 135, steps: int = 12) -> str:
    """Smooth linear gradient, top-left -> bottom-right (Guidelines p.8).
    A smoothstep ease is applied so the transition is a gentle fade, not abrupt."""
    r0, r1 = _rgb(start), _rgb(end)
    stops = []
    for i in range(steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)
        r, g, b = (round(a + (c - a) * e) for a, c in zip(r0, r1))
        stops.append(f"rgb({r},{g},{b}) {t * 100:.1f}%")
    return f"linear-gradient({angle}deg, {', '.join(stops)})"


# Colormaps built only from brand colors. Loss/gain uses red vs. blue (not red vs. green)
# so the maps remain readable for color-blind users.
CMAP_RVI = LinearSegmentedColormap.from_list("palmsar_rvi", [DEEP_BLUE, NEON_BLUE, BLUE_YONDER, NEON_YELLOW])
CMAP_DELTA = LinearSegmentedColormap.from_list("palmsar_delta", [ROCKET_RED, WHITE, BLUE_YONDER])
CMAP_HV = LinearSegmentedColormap.from_list("palmsar_hv", [DEEP_BLUE, BLUE_YONDER, WHITE])

# ------------------------------- Page config --------------------------------
favicon = Image.open(LOGO_SMALL) if LOGO_SMALL.exists() else None
st.set_page_config(
    page_title="PalmSAR Watch | NASA Space Apps Challenge",
    page_icon=favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------- Styling ------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&family=Fira+Sans:wght@700;900&family=Overpass:ital,wght@0,300;0,400;0,600;0,700;1,400&display=swap');

html, body, [class*="css"], .stApp {font-family:'Overpass',sans-serif;color:@@WHITE@@;}
.stApp {background:@@GRADIENT@@;background-attachment:fixed;}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.8rem;padding-bottom:2rem;max-width:1600px;}

/* Typography hierarchy (Guidelines p.13) */
h1, h2 {font-family:'Fira Sans',sans-serif;font-weight:900;text-transform:uppercase;letter-spacing:.05em;color:@@WHITE@@;}
h3 {font-family:'Overpass',sans-serif;font-weight:600;text-transform:uppercase;letter-spacing:.05em;
    font-size:1.25rem;line-height:1.5;color:@@WHITE@@;}
p, li, label, span {font-family:'Overpass',sans-serif;}
pre, code, [data-testid="stCode"] * {font-family:'Fira Code',monospace !important;}

/* Links: Neon Yellow on dark backgrounds, used sparingly (Guidelines p.13) */
.stApp a {color:@@YELLOW@@ !important;text-decoration:underline;font-weight:700;}
.stApp a:hover {color:@@WHITE@@ !important;}

/* Sidebar: Deep Blue, white text */
[data-testid="stSidebar"] {background:@@DEEP@@;border-right:1px solid rgba(46,150,245,.55);}
[data-testid="stSidebar"] * {color:@@WHITE@@;}

/* Tabs */
div[data-testid="stTabs"] button {font-family:'Overpass',sans-serif;font-weight:600;text-transform:uppercase;letter-spacing:.05em;}
div[data-testid="stTabs"] button p {color:@@WHITE@@;}
div[data-testid="stTabs"] button[aria-selected="true"] p {color:@@YELLOW@@;}
[data-baseweb="tab-highlight"] {background-color:@@YELLOW@@ !important;}
[data-baseweb="tab-border"] {background-color:rgba(46,150,245,.45) !important;}

/* Buttons: Neon Yellow with Deep Blue text (Guidelines p.14) */
.stDownloadButton button, .stButton button {
  background:@@YELLOW@@;color:@@DEEP@@;border:0;border-radius:6px;
  font-family:'Overpass',sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:.04em;}
.stDownloadButton button p, .stButton button p {color:@@DEEP@@;font-weight:700;}
.stDownloadButton button:hover, .stButton button:hover {background:@@WHITE@@;color:@@DEEP@@;}

/* Alerts: Deep Blue surface, white text, Neon Yellow accent border (not color-only: icon + text remain) */
div[data-testid="stAlert"], div[data-testid="stAlert"] > div {
  background:@@DEEP@@ !important;color:@@WHITE@@ !important;}
div[data-testid="stAlert"] {border:1px solid @@YELLOW@@;border-radius:10px;}
div[data-testid="stAlert"] p {color:@@WHITE@@ !important;}

/* Code blocks and captions */
[data-testid="stCode"] pre {background:@@DEEP@@ !important;border:1px solid rgba(46,150,245,.5);}
[data-testid="stCaptionContainer"] {color:@@WHITE@@;opacity:.9;}

/* Hero */
.hero {position:relative;overflow:hidden;padding:1.6rem 1.8rem;border:1px solid rgba(46,150,245,.55);
       border-radius:18px;background:@@DEEP@@;}
.hero-pattern {position:absolute;inset:0;opacity:.25;pointer-events:none;
  background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160' fill='none' stroke='white' stroke-width='1'><path d='M26 14v24M14 26h24'/><path d='M118 58v20M108 68h20'/><path d='M62 122v16M54 130h16'/><path d='M140 132v14M133 139h14'/></svg>");}
.hero-inner {position:relative;}
.hero-logo {height:64px;width:auto;display:block;margin:0 0 1.1rem 0;}
.hero-kicker {color:@@YELLOW@@;font-size:.8rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;}
.hero-title {font-family:'Fira Sans',sans-serif;font-size:clamp(2.1rem,5vw,3.75rem);font-weight:900;line-height:1.2;
             text-transform:uppercase;letter-spacing:.05em;color:@@WHITE@@;margin:.25rem 0 .4rem 0;}
.hero-sub {font-family:'Overpass',sans-serif;font-size:clamp(1.1rem,2.6vw,2rem);line-height:1.3;color:@@WHITE@@;}
.hero-sub .accent {color:@@YELLOW@@;display:block;}

/* Cards */
.metric-card {background:@@DEEP@@;border:1px solid rgba(46,150,245,.55);border-radius:14px;padding:1rem 1.1rem;}
.metric-label {color:@@YONDER@@;font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;}
.metric-value {color:@@WHITE@@;font-family:'Fira Sans',sans-serif;font-size:1.55rem;font-weight:700;margin-top:.25rem;}
.metric-note {color:@@WHITE@@;font-weight:300;font-size:.82rem;margin-top:.15rem;}
.section-note {color:@@WHITE@@;font-weight:300;font-size:.95rem;}
.legend-card {background:@@DEEP@@;border:1px solid rgba(46,150,245,.55);border-radius:12px;padding:.7rem 1rem;margin-top:.6rem;}
.legend-title {color:@@WHITE@@;font-size:.85rem;font-weight:600;margin-bottom:.4rem;}
.legend-bar {height:11px;border-radius:8px;}
.legend-scale {display:flex;justify-content:space-between;color:@@WHITE@@;font-size:.78rem;margin-top:.25rem;}
.legend-row {color:@@WHITE@@;font-size:.9rem;}
.footer {margin-top:2rem;padding-top:1rem;border-top:1px solid rgba(46,150,245,.55);
         font-size:.78rem;letter-spacing:.1em;text-transform:uppercase;color:@@WHITE@@;}
</style>
"""
st.markdown(
    CSS.replace("@@GRADIENT@@", eased_gradient_css(ELECTRIC_BLUE, DEEP_BLUE))
       .replace("@@WHITE@@", WHITE).replace("@@YELLOW@@", NEON_YELLOW)
       .replace("@@DEEP@@", DEEP_BLUE).replace("@@YONDER@@", BLUE_YONDER),
    unsafe_allow_html=True,
)


# ------------------------------- Data ---------------------------------------
@st.cache_data(show_spinner=False)
def list_sites() -> dict:
    found = {}
    if not DATA_DIR.exists():
        return found
    for p in DATA_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
            meta["_folder"] = str(p.parent)
            found[meta.get("site_name", p.parent.name)] = meta
        except (OSError, json.JSONDecodeError):
            continue
    return dict(sorted(found.items(), key=lambda item: (item[1].get("synthetic", False), item[0])))


@st.cache_resource(show_spinner="Loading NISAR time-series stack…")
def load_stack(folder: str) -> xr.Dataset:
    path = Path(folder) / "stack.nc"
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    ds = xr.open_dataset(path).load()
    required = {"rvi", "hv_db"}
    missing = required.difference(ds.data_vars)
    if missing:
        raise ValueError(f"Incomplete variables in stack.nc: {', '.join(sorted(missing))}")
    return ds


def rgba_image(array: np.ndarray, cmap, vmin: float, vmax: float, opacity: float):
    safe = np.nan_to_num(array, nan=vmin)
    norm = np.clip((safe - vmin) / (vmax - vmin), 0, 1)
    rgba = cmap(norm)
    rgba[..., 3] = np.where(np.isfinite(array), opacity, 0)
    return (rgba * 255).astype("uint8")


def classes_image(classes: np.ndarray, opacity: float):
    rgba = np.zeros(classes.shape + (4,), dtype="uint8")
    rgba[classes == 1] = (*_rgb(ROCKET_RED), int(255 * opacity))    # loss
    rgba[classes == 2] = (*_rgb(BLUE_YONDER), int(255 * opacity))   # gain
    rgba[classes == 0] = (*_rgb(WHITE), int(150 * opacity))         # stable
    return rgba


def pixel_area_ha(ds: xr.Dataset) -> float:
    # Approximation based on geographic pixel spacing; use projected equal-area
    # measurements for a final area estimate.
    if "lon" not in ds.coords or "lat" not in ds.coords or ds.sizes.get("lon", 0) < 2 or ds.sizes.get("lat", 0) < 2:
        return float("nan")
    dlon = abs(float(ds.lon.values[1] - ds.lon.values[0]))
    dlat = abs(float(ds.lat.values[1] - ds.lat.values[0]))
    lat_c = float(ds.lat.mean())
    return (dlon * 111320 * np.cos(np.radians(lat_c))) * (dlat * 110540) / 10000


def legend_html(cmap, lo: float, hi: float, label: str, lo_text: str = "", hi_text: str = "") -> str:
    stops = ", ".join(matplotlib.colors.to_hex(cmap(v)) for v in np.linspace(0, 1, 9))
    lo_label = f"{lo:g}" + (f" · {lo_text}" if lo_text else "")
    hi_label = f"{hi:g}" + (f" · {hi_text}" if hi_text else "")
    return f"""
    <div class="legend-card">
      <div class="legend-title">{label}</div>
      <div class="legend-bar" style="background:linear-gradient(to right,{stops})"></div>
      <div class="legend-scale"><span>{lo_label}</span><span>{hi_label}</span></div>
    </div>"""


def metric_card(label: str, value: str, note: str = ""):
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


def style_figure(fig: go.Figure, height: int, y_title: str) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height, margin=dict(l=10, r=10, t=25, b=10),
        paper_bgcolor=DEEP_BLUE, plot_bgcolor=DEEP_BLUE,
        font=dict(family="Overpass, sans-serif", color=WHITE, size=14),
        xaxis=dict(title="Observation date", gridcolor="rgba(255,255,255,.15)", zeroline=False),
        yaxis=dict(title=y_title, gridcolor="rgba(255,255,255,.15)", zeroline=False),
        legend=dict(font=dict(color=WHITE)),
    )
    return fig


# -------------------------------- Sidebar -----------------------------------
sites = list_sites()
st.sidebar.markdown("## PalmSAR Watch")
st.sidebar.caption("NISAR L-band · Oil-palm vegetation monitoring")
if not sites:
    st.error(
        f"No data found. Make sure the folder `{DATA_DIR}/<site>/` contains "
        "`stack.nc` and `meta.json`. Run step1–step3 first."
    )
    st.stop()

site = st.sidebar.selectbox("Monitoring area", list(sites))
meta = sites[site]
try:
    ds = load_stack(meta["_folder"])
except Exception as exc:
    st.error(f"Failed to read data: {exc}")
    st.stop()

dates = [str(t)[:10] for t in ds.time.values]
if len(dates) == 0:
    st.error("The stack contains no observation dates.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown("### Layer settings")
layer = st.sidebar.selectbox(
    "Main layer",
    ["Radar Vegetation Index (RVI)", "RVI change (ΔRVI)", "Change classes", "HV backscatter (dB)"],
)
if layer in ("RVI change (ΔRVI)", "Change classes"):
    default_pair = (dates[0], dates[-1])
    date_pair = st.sidebar.select_slider("Comparison range", options=dates, value=default_pair)
    date0, date1 = date_pair
else:
    selected_date = st.sidebar.select_slider("Observation date", options=dates, value=dates[-1])

rvi_thr = 0.25
hv_thr = 3.0
if layer == "Change classes":
    rvi_thr = st.sidebar.slider("ΔRVI threshold", 0.05, 0.60, 0.25, 0.05)
    hv_thr = st.sidebar.slider("ΔHV threshold (dB)", 0.5, 8.0, 3.0, 0.5)
opacity = st.sidebar.slider("Raster opacity", 0.10, 1.00, 0.78, 0.05)
basemap = st.sidebar.radio("Basemap", ["Satellite imagery", "OpenStreetMap"], index=0)

st.sidebar.markdown("---")
st.sidebar.caption(f"Source: {meta.get('source', 'NISAR GCOV')}")
st.sidebar.caption(f"{len(dates)} observation dates · {dates[0]} — {dates[-1]}")
if meta.get("synthetic"):
    st.sidebar.warning("Synthetic / demo data, not actual NISAR observations.")

# ---------------------------- Compose raster --------------------------------
stats = None
if layer == "Radar Vegetation Index (RVI)":
    arr = ds["rvi"].isel(time=dates.index(selected_date)).values
    image = rgba_image(arr, CMAP_RVI, 0.0, 1.2, opacity)
    legend = legend_html(CMAP_RVI, 0.0, 1.2, f"RVI · {selected_date}", "sparse", "dense vegetation")
elif layer == "HV backscatter (dB)":
    arr = ds["hv_db"].isel(time=dates.index(selected_date)).values
    image = rgba_image(arr, CMAP_HV, -25, -8, opacity)
    legend = legend_html(CMAP_HV, -25, -8, f"HV γ⁰ (dB) · {selected_date}", "weak", "strong")
else:
    a = ds.isel(time=dates.index(date0))
    b = ds.isel(time=dates.index(date1))
    delta_rvi = (b["rvi"] - a["rvi"]).values
    if layer == "RVI change (ΔRVI)":
        image = rgba_image(delta_rvi, CMAP_DELTA, -0.6, 0.6, opacity)
        legend = legend_html(CMAP_DELTA, -0.6, 0.6, f"ΔRVI · {date1} minus {date0}", "loss", "gain")
    else:
        delta_hv = (b["hv_db"] - a["hv_db"]).values
        classes = np.zeros(delta_rvi.shape, dtype="uint8")
        valid = np.isfinite(delta_rvi) & np.isfinite(delta_hv)
        classes[~valid] = 255
        classes[valid & (delta_rvi <= -rvi_thr) & (delta_hv <= -hv_thr)] = 1
        classes[valid & (delta_rvi >= rvi_thr) & (delta_hv >= hv_thr)] = 2
        image = classes_image(classes, opacity)
        px_area = pixel_area_ha(ds)
        stats = {
            "loss": int((classes == 1).sum()) * px_area,
            "stable": int((classes == 0).sum()) * px_area,
            "gain": int((classes == 2).sum()) * px_area,
        }
        # Each class is paired with a distinct symbol and a text label, never color alone (Guidelines p.7)
        legend = f"""
        <div class="legend-card">
          <div class="legend-title">Change classes · {date0} → {date1}</div>
          <div class="legend-row">
            <span style="color:{ROCKET_RED}">▼</span> Loss &nbsp;&nbsp;
            <span style="color:{WHITE}">●</span> Stable &nbsp;&nbsp;
            <span style="color:{BLUE_YONDER}">▲</span> Gain
          </div>
        </div>"""

bounds = meta["bounds"]  # [[lat_min, lon_min], [lat_max, lon_max]]

# -------------------------------- Header -------------------------------------
logo_html = ""
if LOGO_DEFAULT.exists():
    b64 = base64.b64encode(LOGO_DEFAULT.read_bytes()).decode()
    # Height only; width stays automatic so the logo is never stretched or distorted.
    logo_html = f'<img class="hero-logo" alt="NASA Space Apps Challenge logo" src="data:image/png;base64,{b64}">'

st.markdown(
    f'<div class="hero"><div class="hero-pattern"></div><div class="hero-inner">'
    f'{logo_html}'
    f'<div class="hero-kicker">Geospatial intelligence · NISAR L-band</div>'
    f'<h1 class="hero-title">PalmSAR Watch</h1>'
    f'<div class="hero-sub"><span class="accent">{site}</span>'
    f'{meta.get("description", "Oil-palm vegetation dynamics monitoring")}</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)
if meta.get("synthetic"):
    st.warning("DEMO MODE — this area uses synthetic data for interface testing.")
st.write("")

# KPI strip
span_days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
k1, k2, k3, k4 = st.columns(4)
with k1:
    metric_card("Observations", f"{len(dates)}", "NISAR dates")
with k2:
    metric_card("Period", f"{span_days} days", f"{dates[0]} to {dates[-1]}")
with k3:
    metric_card("Active layer", layer.split("(")[0].strip(), "Map visualization")
with k4:
    metric_card("Sensor", "NISAR", "L-band · HH/HV dual-pol")

st.write("")
tab_map, tab_temporal, tab_accuracy, tab_method = st.tabs(
    ["Interactive map", "Temporal analysis", "Accuracy validation", "Methods & data"]
)

with tab_map:
    map_col, info_col = st.columns([1.75, 1], gap="large")
    with map_col:
        center = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
        fmap = folium.Map(location=center, zoom_start=11, tiles=None, control_scale=True)
        if basemap == "Satellite imagery":
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri World Imagery", name="Satellite imagery", overlay=False,
            ).add_to(fmap)
        else:
            folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False).add_to(fmap)
        folium.raster_layers.ImageOverlay(
            image=image, bounds=bounds, mercator_project=True, name=layer, interactive=False,
        ).add_to(fmap)
        folium.Rectangle(bounds, color=NEON_YELLOW, weight=2, fill=False, tooltip="Area of Interest").add_to(fmap)
        folium.LayerControl(collapsed=False).add_to(fmap)
        fmap.fit_bounds(bounds)
        map_result = st_folium(
            fmap, height=650, use_container_width=True,
            returned_objects=["last_clicked", "bounds"],
            key=f"map_{site}_{layer}_{opacity}_{date0 if layer in ('RVI change (ΔRVI)','Change classes') else selected_date}",
        )
        st.markdown(legend, unsafe_allow_html=True)

    with info_col:
        st.markdown("### Area summary")
        st.markdown('<div class="section-note">Information follows the selected layer and date.</div>', unsafe_allow_html=True)
        st.write("")
        if stats:
            metric_card("▼ Vegetation loss", f"{stats['loss']:,.1f} ha", "Estimate based on geographic pixel size")
            st.write("")
            metric_card("● Stable vegetation", f"{stats['stable']:,.1f} ha", "Class with no change beyond the thresholds")
            st.write("")
            metric_card("▲ Vegetation gain", f"{stats['gain']:,.1f} ha", "Estimate based on geographic pixel size")
        else:
            metric_card("Active date", selected_date if layer in ("Radar Vegetation Index (RVI)", "HV backscatter (dB)") else f"{date0} → {date1}", "Observation / analysis period")
            st.write("")
            metric_card("Median RVI value", f"{float(ds['rvi'].median().values):.3f}", "Median across all dates and the whole area")
        clicked = (map_result or {}).get("last_clicked")
        if clicked:
            lat, lon = clicked["lat"], clicked["lng"]
            st.write("")
            st.markdown("**Selected coordinates**")
            st.code(f"Latitude : {lat:.6f}\nLongitude: {lon:.6f}")
            iy = int(np.abs(ds.lat.values - lat).argmin())
            ix = int(np.abs(ds.lon.values - lon).argmin())
            point_rvi = ds["rvi"].isel(lat=iy, lon=ix).values
            st.caption(f"Nearest pixel: median RVI = {np.nanmedian(point_rvi):.3f}")

with tab_temporal:
    st.markdown("### Vegetation dynamics over time")
    median_rvi = ds["rvi"].median(dim=("lat", "lon"), skipna=True).values
    mean_hv = ds["hv_db"].mean(dim=("lat", "lon"), skipna=True).values
    temporal = go.Figure()
    temporal.add_trace(go.Scatter(
        x=dates, y=median_rvi, mode="lines+markers", name="Median RVI",
        line=dict(width=3, color=NEON_YELLOW), marker=dict(symbol="circle", size=8),
    ))
    st.plotly_chart(style_figure(temporal, 430, "Median RVI"), use_container_width=True)
    hvfig = go.Figure(go.Scatter(
        x=dates, y=mean_hv, mode="lines+markers", name="Mean HV (dB)",
        line=dict(width=3, color=BLUE_YONDER), marker=dict(symbol="diamond", size=8),
    ))
    st.plotly_chart(style_figure(hvfig, 330, "Mean HV (dB)"), use_container_width=True)
    export_df = pd.DataFrame({"date": dates, "median_rvi": median_rvi, "mean_hv_db": mean_hv})
    st.download_button("Download temporal summary (CSV)", export_df.to_csv(index=False), "palmsar_temporal.csv", "text/csv")

with tab_accuracy:
    st.markdown("### Classification validation results")
    report_path = ROOT / "validation" / os.getenv("PALMSAR_SITE_ID", "sumut_main") / "accuracy_report.txt"
    if report_path.exists():
        st.code(report_path.read_text(encoding="utf-8"), language="text")
    else:
        st.info(
            "Accuracy report not found. Run step4_samples.py, fill in the label column "
            "of the GeoJSON in QGIS (0 = stable, 1 = loss, 2 = gain), then run "
            "step5_accuracy.py. Place the resulting accuracy_report.txt in the folder validation/<site_id>/."
        )
    st.caption("Accuracy is shown only once the reference points have been interpreted and a report is available.")

with tab_method:
    left, right = st.columns(2)
    with left:
        st.markdown("### Data sources and coverage")
        st.write(f"**Source:** {meta.get('source', 'NISAR L2 GCOV')}")
        st.write(f"**Dates:** {dates[0]} to {dates[-1]}")
        st.write(f"**Number of observations:** {len(dates)}")
        st.write(f"**Multilook:** {meta.get('looks', 'Not recorded')} × {meta.get('looks', 'Not recorded')}")
        st.write(f"**AOI bounds:** `{bounds}`")
    with right:
        st.markdown("### Methods")
        st.markdown("""
        1. NISAR Level-2 GCOV dual-polarization HH/HV data.
        2. Speckle reduction through multilooking in linear power.
        3. Radar Vegetation Index calculation: **RVI = 4 × HV / (HH + HV)**.
        4. Change analysis of ΔRVI and ΔHV between dates.
        5. Loss/gain classification based on user-defined change thresholds.
        """)
    st.warning(
        "Note: loss/gain areas in this dashboard are estimates derived from the pixel size "
        "in geographic coordinates. For final reporting, compute areas in an appropriate "
        "projected CRS or use the area values from the GeoTIFF pipeline."
    )
    if meta.get("granules"):
        with st.expander("NISAR granule list"):
            st.code("\n".join(meta["granules"]))

st.markdown(
    '<div class="footer">PalmSAR Innovators · NISAR L-band vegetation monitoring · '
    'Developed for the NASA Space Apps Challenge</div>',
    unsafe_allow_html=True,
)
