"""
PalmSAR Watch — modern WebGIS dashboard
Uses the existing NISAR/RVI NetCDF + metadata export from step3_change_export.py.

Expected data:
    data/<site_id>/stack.nc
    data/<site_id>/meta.json

Run:
    streamlit run app.py
"""
from __future__ import annotations

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
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PALMSAR_DATA_DIR", ROOT / "data"))

st.set_page_config(
    page_title="PalmSAR Watch | Geospatial Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------- Styling ------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {background:#0b1220;}
[data-testid="stHeader"] {background:rgba(11,18,32,.92);}
[data-testid="stSidebar"] {background:#101b2d;border-right:1px solid #26364d;}
[data-testid="stSidebar"] * {color:#e5edf7;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif;letter-spacing:-.03em;}
.hero {padding:1.2rem 1.4rem;border:1px solid #26364d;border-radius:18px;
       background:linear-gradient(120deg,#142b38 0%,#14243a 55%,#1b2d45 100%);}
.hero-kicker {color:#78d6b0;font-size:.76rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;}
.hero-title {font-family:'Space Grotesk',sans-serif;font-size:2rem;font-weight:700;color:#f4f8fc;margin:.2rem 0;}
.hero-sub {color:#a9bbce;font-size:.94rem;}
.metric-card {background:#121f31;border:1px solid #26364d;border-radius:14px;padding:1rem 1.1rem;}
.metric-label {color:#9db0c5;font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;}
.metric-value {color:#f3f7fb;font-family:'Space Grotesk',sans-serif;font-size:1.55rem;font-weight:700;margin-top:.25rem;}
.metric-note {color:#78d6b0;font-size:.75rem;margin-top:.15rem;}
.section-note {color:#9db0c5;font-size:.84rem;}
div[data-testid="stTabs"] button {font-weight:600;}
.block-container {padding-top:1.8rem;padding-bottom:2rem;max-width:1600px;}
</style>
""", unsafe_allow_html=True)


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


def rgba_image(array: np.ndarray, cmap: str, vmin: float, vmax: float, opacity: float):
    safe = np.nan_to_num(array, nan=vmin)
    norm = np.clip((safe - vmin) / (vmax - vmin), 0, 1)
    rgba = matplotlib.colormaps[cmap](norm)
    rgba[..., 3] = np.where(np.isfinite(array), opacity, 0)
    return (rgba * 255).astype("uint8")


def classes_image(classes: np.ndarray, opacity: float):
    rgba = np.zeros(classes.shape + (4,), dtype="uint8")
    rgba[classes == 1] = (215, 25, 28, int(255 * opacity))
    rgba[classes == 2] = (26, 150, 65, int(255 * opacity))
    rgba[classes == 0] = (230, 230, 230, int(150 * opacity))
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


def legend_html(cmap: str, lo: float, hi: float, label: str) -> str:
    stops = ", ".join(matplotlib.colors.to_hex(matplotlib.colormaps[cmap](v)) for v in np.linspace(0, 1, 9))
    return f"""
    <div style="color:#dbe7f3;font-size:.82rem;margin:.55rem 0 .35rem">{label}</div>
    <div style="height:11px;border-radius:8px;background:linear-gradient(to right,{stops})"></div>
    <div style="display:flex;justify-content:space-between;color:#9db0c5;font-size:.72rem">
      <span>{lo:g}</span><span>{hi:g}</span>
    </div>"""


def metric_card(label: str, value: str, note: str = ""):
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


# -------------------------------- Sidebar -----------------------------------
sites = list_sites()
st.sidebar.markdown("## 🛰️ PalmSAR Watch")
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
    image = rgba_image(arr, "YlGn", 0.0, 1.2, opacity)
    legend = legend_html("YlGn", 0.0, 1.2, f"RVI · {selected_date}")
elif layer == "HV backscatter (dB)":
    arr = ds["hv_db"].isel(time=dates.index(selected_date)).values
    image = rgba_image(arr, "gray", -25, -8, opacity)
    legend = legend_html("gray", -25, -8, f"HV γ⁰ (dB) · {selected_date}")
else:
    a = ds.isel(time=dates.index(date0))
    b = ds.isel(time=dates.index(date1))
    delta_rvi = (b["rvi"] - a["rvi"]).values
    if layer == "RVI change (ΔRVI)":
        image = rgba_image(delta_rvi, "RdYlGn", -0.6, 0.6, opacity)
        legend = legend_html("RdYlGn", -0.6, 0.6, f"ΔRVI · {date1} minus {date0}")
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
        legend = """
        <div style="font-size:.82rem;color:#dbe7f3;margin:.5rem 0">
        <span style="color:#d7191c">■</span> Loss &nbsp;
        <span style="color:#e6e6e6">■</span> Stable &nbsp;
        <span style="color:#1a9641">■</span> Gain</div>"""

bounds = meta["bounds"]  # [[lat_min, lon_min], [lat_max, lon_max]]

# -------------------------------- Header -------------------------------------
st.markdown(
    f'<div class="hero"><div class="hero-kicker">Geospatial intelligence · NISAR L-band</div>'
    f'<div class="hero-title">PalmSAR Watch</div>'
    f'<div class="hero-sub">{site} · {meta.get("description", "Oil-palm vegetation dynamics monitoring")}</div></div>',
    unsafe_allow_html=True,
)
if meta.get("synthetic"):
    st.warning("DEMO MODE — this area uses synthetic data for interface testing.")
st.write("")

# KPI strip
k1, k2, k3, k4 = st.columns(4)
with k1:
    metric_card("Observations", f"{len(dates)}", "NISAR dates")
with k2:
    metric_card("Period", f"{len(dates)}", f"{dates[0]} to {dates[-1]}")
with k3:
    metric_card("Active layer", layer.split("(")[0].strip(), "Map visualization")
with k4:
    metric_card("Temporal resolution", "NISAR", "Time series follows available data")

st.write("")
tab_map, tab_temporal, tab_accuracy, tab_method = st.tabs(
    ["🗺️ Interactive map", "📈 Temporal analysis", "🎯 Accuracy validation", "ⓘ Methods & data"]
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
        folium.Rectangle(bounds, color="#55d6a6", weight=2, fill=False, tooltip="Area of Interest").add_to(fmap)
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
        if stats:
            metric_card("Vegetation loss", f"{stats['loss']:,.1f} ha", "Estimate based on geographic pixel size")
            st.write("")
            metric_card("Stable vegetation", f"{stats['stable']:,.1f} ha", "Class with no change beyond the thresholds")
            st.write("")
            metric_card("Vegetation gain", f"{stats['gain']:,.1f} ha", "Estimate based on geographic pixel size")
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
    temporal.add_trace(go.Scatter(x=dates, y=median_rvi, mode="lines+markers", name="Median RVI", line=dict(width=3)))
    temporal.update_layout(
        template="plotly_dark", height=430, margin=dict(l=10, r=10, t=25, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(18,31,49,.55)",
        xaxis_title="Observation date", yaxis_title="Median RVI",
    )
    st.plotly_chart(temporal, use_container_width=True)
    hvfig = go.Figure(go.Scatter(x=dates, y=mean_hv, mode="lines+markers", name="Mean HV (dB)"))
    hvfig.update_layout(
        template="plotly_dark", height=330, margin=dict(l=10, r=10, t=25, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(18,31,49,.55)",
        xaxis_title="Observation date", yaxis_title="Mean HV (dB)",
    )
    st.plotly_chart(hvfig, use_container_width=True)
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
    st.markdown("**PalmSAR Innovators · NISAR L-band vegetation monitoring**")
