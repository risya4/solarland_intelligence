import io
import json
import math
import time
from typing import Optional, Tuple

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from folium.plugins import Fullscreen, MeasureControl
from pyproj import Geod
from shapely.geometry import shape
from streamlit_folium import st_folium

# =========================================================
# SOLARLAND INTELLIGENCE
# Perkasa Land Development
# =========================================================

st.set_page_config(
    page_title="SolarLand Intelligence",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

GREEN = "#176B45"
DARK_GREEN = "#104B34"
LIGHT_GREEN = "#EAF5EE"
GOLD = "#D7A928"
RED = "#C94C4C"
GEOD = Geod(ellps="WGS84")
SQM_PER_ACRE = 4046.8564224

# ------------------------- Styling -------------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
    .stApp {{ background: #F6F8F6; }}
    [data-testid="stSidebar"] {{ background: #103F2E; }}
    [data-testid="stSidebar"] * {{ color: #FFFFFF !important; }}
    [data-testid="stSidebar"] [data-baseweb="input"] input,
    [data-testid="stSidebar"] [data-baseweb="select"] div {{
        color: #163D2B !important;
    }}
    .hero {{
        background: linear-gradient(115deg, #104B34 0%, #176B45 65%, #2D8B5C 100%);
        padding: 1.45rem 1.7rem; border-radius: 18px; color: white;
        margin-bottom: 1.2rem; box-shadow: 0 8px 22px rgba(16,75,52,.12);
    }}
    .hero h1 {{ color: white; font-size: 2rem; margin: 0 0 .25rem 0; }}
    .hero p {{ color: #E5F3E9; margin: 0; }}
    .eyebrow {{ color: #D9EBDD; text-transform: uppercase; letter-spacing: 1.6px;
        font-size: .72rem; font-weight: 700; }}
    .section-kicker {{ color: #52715F; text-transform: uppercase;
        letter-spacing: 1.2px; font-size: .72rem; font-weight: 700; }}
    .small-note {{ color: #64746A; font-size: .82rem; }}
    div[data-testid="stMetric"] {{
        background: white; border: 1px solid #E5ECE6; padding: 14px 16px;
        border-radius: 13px; box-shadow: 0 2px 8px rgba(16,75,52,.035);
    }}
    div[data-testid="stMetricLabel"] {{ color: #64746A; }}
    div[data-testid="stMetricValue"] {{ color: #104B34; }}
    .stButton > button, .stDownloadButton > button {{
        border-radius: 9px; border: 1px solid #176B45; font-weight: 600;
    }}
    .stButton > button[kind="primary"] {{
        background: #176B45; color: white; border: none;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------- Helpers -------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class GeocodingUnavailableError(RuntimeError):
    """Raised when all configured place-search services are unavailable."""


@st.cache_data(ttl=86400, show_spinner=False)
def geocode_place(query: str) -> Optional[Tuple[float, float, str]]:
    """
    Resolve a place name using Nominatim, then Photon as a fallback.
    Results are cached for 24 hours to reduce repeated public API requests.
    """
    query = (query or "").strip()
    if not query:
        return None

    headers = {
        "User-Agent": "SolarLandIntelligence/1.0 (land suitability screening prototype)",
        "Accept": "application/json",
        "Accept-Language": "en",
    }
    errors = []

    # Primary provider: OpenStreetMap Nominatim.
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1},
            headers=headers,
            timeout=(5, 12),
        )
        response.raise_for_status()
        results = response.json()
        if results:
            item = results[0]
            return (
                float(item["lat"]),
                float(item["lon"]),
                item.get("display_name", query),
            )
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Nominatim: {type(exc).__name__}")

    # Fallback provider: Photon (Komoot), independent of Nominatim.
    try:
        response = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 1, "lang": "en"},
            headers=headers,
            timeout=(5, 12),
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        if features:
            feature = features[0]
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            if len(coordinates) >= 2:
                props = feature.get("properties", {})
                label_parts = [
                    props.get("name"),
                    props.get("city") or props.get("district"),
                    props.get("state"),
                    props.get("country"),
                ]
                label = ", ".join(dict.fromkeys(x for x in label_parts if x)) or query
                return float(coordinates[1]), float(coordinates[0]), label
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Photon: {type(exc).__name__}")

    if errors:
        raise GeocodingUnavailableError(
            "Location search services could not be reached. Please try again later "
            "or enter the PMU latitude and longitude manually."
        )
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def road_distance_km(origin, destination):
    """Try OSRM public demo routing service. Returns None when unavailable."""
    # OSRM coordinates are longitude,latitude
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    )
    try:
        response = requests.get(
            url,
            params={"overview": "false", "alternatives": "false", "steps": "false"},
            headers={"User-Agent": "SolarLandIntelligence/1.0"},
            timeout=18,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") == "Ok" and payload.get("routes"):
            return round(payload["routes"][0]["distance"] / 1000, 2)
    except requests.RequestException:
        return None
    return None


def polygon_area_acres(geometry):
    try:
        geom = shape(geometry)
        if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid:
            return None
        area_sqm, _ = GEOD.geometry_area_perimeter(geom)
        return round(abs(area_sqm) / SQM_PER_ACRE, 2)
    except Exception:
        return None


def polygon_center(geometry):
    geom = shape(geometry)
    pt = geom.representative_point()
    return float(pt.y), float(pt.x)


def classify_land(acres, distance_km, min_acres, max_acres, preferred_km, max_km):
    # Do not substitute straight-line distance for a road-distance decision.
    if pd.isna(acres) or pd.isna(distance_km):
        return "Pending Verification"
    size_ok = min_acres <= float(acres) <= max_acres
    if size_ok and float(distance_km) <= preferred_km:
        return "Good Fit"
    if size_ok and float(distance_km) <= max_km:
        return "Worth a Look"
    return "No Good"


def sample_data():
    # Illustrative points only; not verified vacant parcels or surveyed boundaries.
    return pd.DataFrame({
        "Land ID": ["DEMO-001", "DEMO-002", "DEMO-003", "DEMO-004", "DEMO-005", "DEMO-006"],
        "Land Name": ["Demo Parcel A", "Demo Parcel B", "Demo Parcel C", "Demo Parcel D", "Demo Parcel E", "Demo Parcel F"],
        "Latitude": [6.4550, 6.4750, 6.4900, 6.4400, 6.5100, 6.4620],
        "Longitude": [100.4250, 100.4350, 100.4500, 100.4100, 100.4600, 100.4050],
        "Land Size (Acres)": [90, 85, 120, 75, 95, 82],
        "State": ["Kedah"] * 6,
        "District": ["Kubang Pasu"] * 6,
        "Verification Status": ["Illustrative - Not Verified"] * 6,
        "Data Source": ["Illustrative sample"] * 6,
    })


def normalize_csv(df):
    aliases = {
        "land id": "Land ID", "id": "Land ID",
        "land name": "Land Name", "name": "Land Name", "parcel": "Land Name",
        "latitude": "Latitude", "lat": "Latitude",
        "longitude": "Longitude", "lon": "Longitude", "lng": "Longitude",
        "land size (acres)": "Land Size (Acres)", "acres": "Land Size (Acres)",
        "area acres": "Land Size (Acres)",
    }
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in aliases:
            rename[col] = aliases[key]
    df = df.rename(columns=rename).copy()
    required = ["Latitude", "Longitude"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("CSV mesti mempunyai kolum Latitude dan Longitude.")
    if "Land Name" not in df.columns:
        df["Land Name"] = [f"Parcel {i+1}" for i in range(len(df))]
    if "Land ID" not in df.columns:
        df["Land ID"] = [f"PARCEL-{i+1:03d}" for i in range(len(df))]
    if "Land Size (Acres)" not in df.columns:
        df["Land Size (Acres)"] = pd.NA
    for c in ["Latitude", "Longitude", "Land Size (Acres)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "State" not in df.columns:
        df["State"] = "Not specified"
    if "District" not in df.columns:
        df["District"] = "Not specified"
    if "Verification Status" not in df.columns:
        df["Verification Status"] = "Unverified - User supplied"
    if "Data Source" not in df.columns:
        df["Data Source"] = "User-uploaded CSV"
    df = df.dropna(subset=["Latitude", "Longitude"])
    df = df[df["Latitude"].between(-90, 90) & df["Longitude"].between(-180, 180)]
    return df.reset_index(drop=True)


def load_geojson(upload):
    raw = json.load(upload)
    features = raw.get("features", []) if raw.get("type") == "FeatureCollection" else []
    rows = []
    for i, feature in enumerate(features):
        geom = feature.get("geometry")
        if not geom:
            continue
        props = feature.get("properties") or {}
        try:
            lat, lon = polygon_center(geom)
            acres = polygon_area_acres(geom)
        except Exception:
            continue
        rows.append({
            "Land ID": str(props.get("id", f"GEO-{i+1:03d}")),
            "Land Name": str(props.get("name", props.get("lot_no", f"GeoJSON Parcel {i+1}"))),
            "Latitude": lat,
            "Longitude": lon,
            "Land Size (Acres)": acres,
            "State": str(props.get("state", "Not specified")),
            "District": str(props.get("district", "Not specified")),
            "Verification Status": str(props.get("verification_status", "Unverified - User supplied")),
            "Data Source": str(props.get("data_source", "Uploaded GeoJSON polygon")),
        })
    if not rows:
        raise ValueError("GeoJSON tidak mengandungi polygon yang sah.")
    return pd.DataFrame(rows)


# ------------------------- Header -------------------------
st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Perkasa Land Development</div>
      <h1>☀️ SolarLand Intelligence</h1>
      <p>Land suitability screening for potential solar farm development</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Prototype notice: this tool supports preliminary screening only. "
    "A parcel shown on the map is not proof that the land is vacant, available, "
    "owned by a willing seller, legally developable, or suitable for a solar project."
)

# ------------------------- Sidebar controls -------------------------
st.sidebar.markdown("## ☀️ SolarLand")
st.sidebar.caption("Land Intelligence Workspace")
page = st.sidebar.radio(
    "Navigation",
    ["Overview", "PMU Configuration", "Land Explorer", "Land Evaluation", "Export Evaluation Results"],
)
st.sidebar.divider()
st.sidebar.markdown("### PMU location")
MALAYSIA_STATES = [
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan",
    "Pahang", "Perak", "Perlis", "Pulau Pinang", "Sabah",
    "Sarawak", "Selangor", "Terengganu", "W.P. Kuala Lumpur",
    "W.P. Labuan", "W.P. Putrajaya"
]
selected_state = st.sidebar.selectbox("State / Federal Territory", MALAYSIA_STATES, index=1)
selected_district = st.sidebar.text_input("District / area (optional)", "Kubang Pasu")
pmu_name = st.sidebar.text_input("PMU / target location name", "PMU Bukit Kayu Hitam")
coord_mode = st.sidebar.radio("Location input", ["Enter coordinates", "Search place name"])
if coord_mode == "Enter coordinates":
    pmu_lat = st.sidebar.number_input("Latitude", value=6.4500, format="%.6f")
    pmu_lon = st.sidebar.number_input("Longitude", value=100.4200, format="%.6f")
    resolved_label = "Coordinates entered by user"
else:
    place_query = st.sidebar.text_input("Search location", f"{pmu_name}, {selected_district}, {selected_state}, Malaysia")
    if st.sidebar.button("Find location", type="primary", use_container_width=True):
        try:
            found = geocode_place(place_query)
            if found:
                st.session_state["pmu_geocode"] = found
                st.sidebar.success("Location found.")
            else:
                st.sidebar.warning("No matching place found. Try a more specific name.")
        except GeocodingUnavailableError as exc:
            st.sidebar.error(str(exc))
        except Exception:
            st.sidebar.error(
                "Location search could not be completed. Please try a more specific "
                "place name or enter coordinates manually."
            )
    stored = st.session_state.get("pmu_geocode", (6.4500, 100.4200, "Default example coordinates"))
    pmu_lat, pmu_lon, resolved_label = stored
    st.sidebar.caption(f"Resolved: {resolved_label[:90]}")

st.sidebar.divider()
st.sidebar.markdown("### Screening criteria")
min_acres = st.sidebar.number_input("Minimum preferred land size (acres)", min_value=0.0, value=80.0, step=5.0)
max_acres = st.sidebar.number_input("Maximum preferred land size (acres)", min_value=0.0, value=100.0, step=5.0)
preferred_km = st.sidebar.number_input("Preferred road distance (km)", min_value=0.1, value=5.0, step=0.5)
max_km = st.sidebar.number_input("Maximum road distance (km)", min_value=preferred_km, value=max(8.0, preferred_km), step=0.5)
use_osrm = st.sidebar.checkbox("Try road routing (OSRM public demo)", value=True)
if min_acres > max_acres:
    st.sidebar.error("Minimum acres cannot exceed maximum acres.")

# ------------------------- Data input -------------------------
st.sidebar.divider()
st.sidebar.markdown("### Land data")
data_mode = st.sidebar.radio("Data source", ["Illustrative demo data", "Upload CSV", "Upload GeoJSON"])
uploaded_df = None
if data_mode == "Upload CSV":
    csv_file = st.sidebar.file_uploader("Upload parcel CSV", type=["csv"])
    if csv_file:
        try:
            uploaded_df = normalize_csv(pd.read_csv(csv_file))
        except Exception as e:
            st.sidebar.error(str(e))
elif data_mode == "Upload GeoJSON":
    geo_file = st.sidebar.file_uploader("Upload parcel GeoJSON", type=["geojson", "json"])
    if geo_file:
        try:
            uploaded_df = load_geojson(geo_file)
        except Exception as e:
            st.sidebar.error(str(e))

if data_mode == "Illustrative demo data":
    land_df = sample_data()
elif uploaded_df is not None:
    land_df = uploaded_df.copy()
else:
    land_df = pd.DataFrame(columns=["Land ID", "Land Name", "Latitude", "Longitude", "Land Size (Acres)", "Data Source"])

# ------------------------- Analysis pipeline -------------------------
if not land_df.empty and min_acres <= max_acres:
    land_df["Straight-line Distance (km)"] = land_df.apply(
        lambda r: haversine_km(pmu_lat, pmu_lon, r["Latitude"], r["Longitude"]), axis=1
    )
    road_values = []
    distance_types = []
    for _, row in land_df.iterrows():
        road = road_distance_km((pmu_lat, pmu_lon), (row["Latitude"], row["Longitude"])) if use_osrm else None
        if road is not None:
            road_values.append(road)
            distance_types.append("OSRM driving route")
        else:
            road_values.append(pd.NA)
            distance_types.append("Unavailable - route not returned")
        if use_osrm:
            time.sleep(0.20)
    land_df["Road Distance / Estimate (km)"] = road_values
    land_df["Distance Method"] = distance_types
    land_df["Classification"] = land_df.apply(
        lambda r: classify_land(
            r["Land Size (Acres)"], r["Road Distance / Estimate (km)"],
            min_acres, max_acres, preferred_km, max_km
        ), axis=1
    )
    land_df["Distance (km)"] = land_df["Road Distance / Estimate (km)"]
    rank = {"Good Fit": 1, "Worth a Look": 2, "No Good": 3, "Pending Verification": 4}
    land_df["Rank"] = land_df["Classification"].map(rank)
    land_df = land_df.sort_values(
        ["Rank", "Distance (km)"], ascending=[True, True], na_position="last"
    ).reset_index(drop=True)

# ------------------------- Page: Overview -------------------------
if page == "Overview":
    st.markdown('<div class="section-kicker">Overview</div>', unsafe_allow_html=True)
    st.subheader("Land Intelligence Overview")
    if land_df.empty:
        st.warning("No parcel data loaded. Select demo data or upload a CSV / GeoJSON in the sidebar.")
    else:
        total = len(land_df)
        good = int((land_df["Classification"] == "Good Fit").sum())
        look = int((land_df["Classification"] == "Worth a Look").sum())
        no_good = int((land_df["Classification"] == "No Good").sum())
        pending = int((land_df["Classification"] == "Pending Verification").sum())
        known_acres = pd.to_numeric(land_df["Land Size (Acres)"], errors="coerce").sum()
        c1, c2, c3, c4, c5m = st.columns(5)
        c1.metric("Parcels screened", total)
        c2.metric("Good Fit", good)
        c3.metric("Worth a Look", look)
        c4.metric("No Good", no_good)
        c5m.metric("Pending verification", pending)
        c5, c6 = st.columns(2)
        c5.metric("Total listed area", f"{known_acres:,.2f} acres")
        c6.metric("PMU reference", pmu_name)
        left, right = st.columns([1.35, 1])
        with left:
            st.markdown("#### Suitability distribution")
            counts = land_df["Classification"].value_counts().reindex(
                ["Good Fit", "Worth a Look", "No Good", "Pending Verification"], fill_value=0
            ).rename_axis("Classification").reset_index(name="Parcels")
            fig = px.bar(
                counts, x="Classification", y="Parcels", color="Classification",
                color_discrete_map={"Good Fit": GREEN, "Worth a Look": GOLD, "No Good": RED, "Pending Verification": "#7A8790"},
            )
            fig.update_layout(
                showlegend=False, margin=dict(l=10, r=10, t=20, b=10),
                paper_bgcolor="white", plot_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("#### Highest-ranked parcels")
            st.dataframe(
                land_df[["Land ID", "Land Name", "Land Size (Acres)", "Distance (km)", "Classification"]].head(5),
                hide_index=True, use_container_width=True
            )
        methods = land_df["Distance Method"].value_counts().to_dict()
        st.caption("Distance method used: " + "; ".join([f"{k}: {v}" for k, v in methods.items()]))
        if data_mode == "Illustrative demo data":
            st.warning("Demo dataset selected: parcel names, locations and areas are illustrative, not verified land records.")

# ------------------------- Page: PMU Configuration -------------------------
elif page == "PMU Configuration":
    st.markdown('<div class="section-kicker">Configuration</div>', unsafe_allow_html=True)
    st.subheader("PMU Location & Evaluation Parameters")
    st.write("Configure the PMU location and evaluation parameters using the sidebar. Results will automatically update based on the selected criteria.")
    st.markdown("#### Current PMU")
    st.write(f"**Name:** {pmu_name}")
    st.write(f"**State / District:** {selected_state} / {selected_district or 'Not specified'}")
    st.write(f"**Latitude:** {pmu_lat:.6f}  ·  **Longitude:** {pmu_lon:.6f}")
    st.write(f"**Location source:** {resolved_label}")
    st.markdown("#### Screening thresholds")
    st.write(f"- Preferred land size: **{min_acres:g}–{max_acres:g} acres**")
    st.write(f"- Preferred distance: **within {preferred_km:g} km**")
    st.write(f"- Maximum distance: **within {max_km:g} km**")
    st.info("These thresholds follow the assessment brief. They are screening rules, not a legal or engineering approval.")

# ------------------------- Page: Land Explorer -------------------------
elif page == "Land Explorer":
    st.markdown('<div class="section-kicker">Geospatial workspace</div>', unsafe_allow_html=True)
    st.subheader("Land parcel explorer")
    if land_df.empty:
        st.warning("Load parcel data using the sidebar.")
    else:
        st.caption("Green circle = preferred distance zone. Amber circle = maximum reference zone. Parcel markers are coloured by screening result.")
        fmap = folium.Map(location=[pmu_lat, pmu_lon], zoom_start=11, control_scale=True, tiles="OpenStreetMap")
        folium.Marker(
            [pmu_lat, pmu_lon], tooltip=f"PMU: {pmu_name}",
            popup=f"<b>{pmu_name}</b><br>Reference location",
            icon=folium.Icon(color="blue", icon="bolt", prefix="fa"),
        ).add_to(fmap)
        folium.Circle(
            [pmu_lat, pmu_lon], radius=preferred_km * 1000,
            color=GREEN, fill=True, fill_opacity=0.08,
            tooltip=f"Preferred zone: {preferred_km:g} km",
        ).add_to(fmap)
        folium.Circle(
            [pmu_lat, pmu_lon], radius=max_km * 1000,
            color=GOLD, fill=True, fill_opacity=0.04,
            tooltip=f"Maximum zone: {max_km:g} km",
        ).add_to(fmap)
        marker_colors = {"Good Fit": "green", "Worth a Look": "orange", "No Good": "red", "Pending Verification": "gray"}
        for _, row in land_df.iterrows():
            road_distance = row["Distance (km)"]
            distance_label = (
                f"{float(road_distance):.2f} km"
                if pd.notna(road_distance) else "Unavailable"
            )
            area_value = row["Land Size (Acres)"]
            area_label = (
                f"{float(area_value):.2f} acres"
                if pd.notna(area_value) else "Not provided"
            )
            popup = (
                f"<b>{row['Land Name']}</b><br>"
                f"ID: {row['Land ID']}<br>"
                f"Area: {area_label}<br>"
                f"Road distance: {distance_label}<br>"
                f"Method: {row['Distance Method']}<br>"
                f"Verification: {row.get('Verification Status', 'Unverified')}<br>"
                f"Result: {row['Classification']}"
            )
            folium.Marker(
                [row["Latitude"], row["Longitude"]],
                tooltip=str(row["Land Name"]),
                popup=folium.Popup(popup, max_width=300),
                icon=folium.Icon(color=marker_colors[row["Classification"]], icon="map-marker", prefix="fa"),
            ).add_to(fmap)
        Fullscreen(position="topright").add_to(fmap)
        MeasureControl(position="bottomleft", primary_length_unit="kilometers").add_to(fmap)
        folium.LayerControl().add_to(fmap)
        st_folium(fmap, use_container_width=True, height=590, returned_objects=[])
        st.caption("Map tiles and location services require an internet connection. The circles show straight-line radius zones, not road-network buffers.")

# ------------------------- Page: Land Evaluation -------------------------
elif page == "Land Evaluation":
    st.markdown('<div class="section-kicker">Screening output</div>', unsafe_allow_html=True)
    st.subheader("Ranked Land Evaluation")
    if land_df.empty:
        st.warning("Load parcel data using the sidebar.")
    else:
        st.caption("Classification uses the preferred area range and a returned OSRM driving-route distance. If road routing is unavailable, the parcel remains Pending Verification; straight-line distance is shown separately only as a reference.")
        filter_status = st.multiselect(
            "Filter classification",
            ["Good Fit", "Worth a Look", "No Good", "Pending Verification"],
            default=["Good Fit", "Worth a Look", "No Good", "Pending Verification"],
        )
        filtered = land_df[land_df["Classification"].isin(filter_status)]
        cols = ["Rank", "Land ID", "Land Name", "State", "District", "Land Size (Acres)", "Straight-line Distance (km)",
                "Road Distance / Estimate (km)", "Distance Method", "Classification", "Verification Status", "Data Source"]
        st.dataframe(filtered[cols].round(2), use_container_width=True, hide_index=True)
        st.markdown("#### Classification logic")
        st.markdown(
            f"- **Good Fit:** {min_acres:g}–{max_acres:g} acres and distance ≤ {preferred_km:g} km.\n"
            f"- **Worth a Look:** {min_acres:g}–{max_acres:g} acres and distance > {preferred_km:g} km but ≤ {max_km:g} km.\n"
            f"- **No Good:** outside the preferred size range or beyond {max_km:g} km, or missing area data."
        )
        st.caption("This is a simplified initial-screening rule. Parcels without a returned road route or confirmed area remain Pending Verification. Terrain, land title, zoning, flood risk, access rights, grid capacity, environmental constraints and site inspections are not assessed.")

# ------------------------- Page: Export Evaluation Results -------------------------
elif page == "Export Evaluation Results":
    st.markdown('<div class="section-kicker">Reporting</div>', unsafe_allow_html=True)
    st.subheader("Export Evaluation Results")
    if land_df.empty:
        st.warning("No results available to export. Load parcel data first.")
    else:
        st.write("Download the current results as an Excel workbook or CSV file.")
        report = land_df.copy()
        report["PMU Name"] = pmu_name
        report["PMU Latitude"] = pmu_lat
        report["PMU Longitude"] = pmu_lon
        report["Minimum Preferred Acres"] = min_acres
        report["Maximum Preferred Acres"] = max_acres
        report["Preferred Distance (km)"] = preferred_km
        report["Maximum Distance (km)"] = max_km
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            report.to_excel(writer, index=False, sheet_name="Land Evaluation")
            criteria = pd.DataFrame({
                "Parameter": ["PMU Name", "PMU Latitude", "PMU Longitude", "Minimum Acres",
                              "Maximum Acres", "Preferred Distance km", "Maximum Distance km",
                              "Data Mode", "Generated Note"],
                "Value": [pmu_name, pmu_lat, pmu_lon, min_acres, max_acres,
                          preferred_km, max_km, data_mode,
                          "Preliminary screening only; verify all parcels independently."],
            })
            criteria.to_excel(writer, index=False, sheet_name="Criteria & Notes")
        st.download_button(
            "⬇ Download Evaluation Workbook",
            data=buffer.getvalue(),
            file_name="SolarLand_Intelligence.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        st.download_button(
            "⬇ Download CSV results",
            data=report.to_csv(index=False).encode("utf-8-sig"),
            file_name="SolarLand_Intelligence.csv",
            mime="text/csv",
        )
        st.caption("The workbook includes the parcel results and a separate sheet recording the PMU and screening criteria.")

# ------------------------- Footer -------------------------
st.divider()
st.caption(
    "SolarLand Intelligence"
    "Public data/services are subject to availability and their own terms. "
    "No confidential or restricted data should be uploaded."
)
