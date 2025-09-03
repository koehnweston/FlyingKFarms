import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
import io
import requests
from datetime import date, timedelta
import tempfile
import os
import folium
from streamlit_folium import st_folium
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- Page Configuration ---
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

# --- API Key Configuration ---
OPENET_API_KEY = st.secrets.get("OPENET_API_KEY")

# --- Data Loading ---
SHAPEFILE_URL = "https://raw.githubusercontent.com/koehnweston/FlyingKFarms/main/parcels_2.zip"

@st.cache_data
def load_data_from_github(url):
    """
    Loads, processes, and re-projects a zipped shapefile from a GitHub URL.
    """
    tmp_path = None
    try:
        response = requests.get(url)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            shapefile_name = next((name for name in zf.namelist() if name.lower().endswith('.shp')), None)
            if not shapefile_name:
                st.error("Error: No .shp file found inside the zip archive.")
                return None
        uri = f"zip://{tmp_path}!{shapefile_name}"
        gdf = gpd.read_file(uri)
        if gdf.crs is None:
            st.info("Shapefile CRS not found. Assuming KS State Plane North (EPSG:2241).")
            gdf.set_crs(epsg=2241, inplace=True)
        gdf = gdf.to_crs(epsg=4326)
        return gdf
    except Exception as e:
        st.error(f"An error occurred during data loading: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

def make_openet_api_call(payload, api_key):
    """
    A generic function to make a POST request to the OpenET API.
    """
    API_URL = "https://openet-api.org/raster/timeseries/point"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"OpenET API Error for variable {payload.get('variable')}: {e}")
        if e.response:
            st.error(f"Status Code: {e.response.status_code}")
            try:
                st.json(e.response.json())
            except json.JSONDecodeError:
                st.text(e.response.text)
        return None

@st.cache_data
def fetch_et_data(_geometry, start_date, end_date, api_key):
    """Fetches daily ET data in inches."""
    payload = {
        "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
        "geometry": [_geometry.centroid.x, _geometry.centroid.y],
        "interval": "daily",
        "model": "Ensemble",
        "reference_et": "gridMET",
        "variable": "ET",
        "units": "inches" # CHANGED
    }
    data = make_openet_api_call(payload, api_key)
    if data:
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        df.rename(columns={'et': 'ET (in)'}, inplace=True)
        return df[['ET (in)']]
    return None

@st.cache_data
def fetch_ndvi_data(_geometry, start_date, end_date, api_key):
    """Fetches daily NDVI data."""
    payload = {
        "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
        "geometry": [_geometry.centroid.x, _geometry.centroid.y],
        "interval": "daily",
        "model": "landsat",
        "variable": "NDVI" # CHANGED
    }
    data = make_openet_api_call(payload, api_key)
    if data:
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        df.rename(columns={'ndvi': 'NDVI'}, inplace=True)
        return df[['NDVI']]
    return None

# --- Main App ---
st.markdown("# 🌾 Farming Data Entry")

# --- Sidebar ---
st.sidebar.header("Field Setup")
st.sidebar.info("Field data is automatically loaded from GitHub.")
st.session_state.debug_mode = st.sidebar.checkbox("Enable Debug Mode")
if st.sidebar.button("Clear Cache & Reload Data"):
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()

if 'data_loaded' not in st.session_state:
    with st.spinner("Loading field data from GitHub..."):
        gdf = load_data_from_github(SHAPEFILE_URL)
        if gdf is not None:
            column_map = {col.lower(): col for col in gdf.columns}
            if 'section' in column_map:
                gdf.rename(columns={column_map['section']: 'Section'}, inplace=True)
            if 'area' in column_map:
                gdf.rename(columns={column_map['area']: 'Area'}, inplace=True)
            if 'geometry' in gdf.columns and not gdf.empty:
                centroids = gdf.geometry.centroid
                gdf['X'] = centroids.x
                gdf['Y'] = centroids.y
            st.session_state.gdf = gdf
            if "Section" in gdf.columns:
                st.session_state.field_options = sorted(gdf["Section"].unique().tolist())
                st.sidebar.success(f"Loaded {len(st.session_state.field_options)} unique sections.")
            else:
                st.sidebar.error("Shapefile is missing the 'Section' column.")
                st.session_state.field_options = []
        else:
            st.sidebar.error("Failed to load shapefile from GitHub.")
    st.session_state.data_loaded = True

# --- Main Content ---
if not st.session_state.get('field_options'):
    st.warning("Could not load field data. Please check the configuration.")
else:
    data_type = st.selectbox(
        "Select Data Type",
        ["Water Usage", "Crop Data", "Soil Data", "Fertilizer Data", "Yield Data", "OpenET Data"]
    )
    st.markdown("---")
    st.subheader("Field Information")
    selected_section = st.selectbox("Select Field Section", options=st.session_state.field_options, index=0)

    if selected_section and st.session_state.gdf is not None:
        section_data = st.session_state.gdf[st.session_state.gdf["Section"] == selected_section].iloc[0]
        col1, col2, col3 = st.columns(3)
        col1.metric("X", f"{section_data.get('X', 0):.4f}")
        col2.metric("Y", f"{section_data.get('Y', 0):.4f}")
        col3.metric("Area", f"{section_data.get('Area', 0):.2f}")
        st.markdown("##### Field Map")
        map_center = [section_data.geometry.centroid.y, section_data.geometry.centroid.x]
        m = folium.Map(location=map_center, zoom_start=15, tiles=None)
        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Esri Satellite').add_to(m)
        folium.GeoJson(section_data.geometry, style_function=lambda x: {'fillColor': 'cyan', 'color': 'blue', 'weight': 2.5, 'fillOpacity': 0.4}).add_to(m)
        st_folium(m, key=selected_section, width=725, height=500)

    st.markdown(f"### Enter {data_type}")

    # --- OpenET Data Section ---
    if data_type == "OpenET Data":
        if not OPENET_API_KEY:
            st.error("OpenET API key not configured in Streamlit secrets.")
        else:
            today = date.today()
            one_year_ago = today - timedelta(days=365)
            dcol1, dcol2 = st.columns(2)
            start_date = dcol1.date_input("Start Date", one_year_ago)
            end_date = dcol2.date_input("End Date", today)

            if start_date > end_date:
                st.warning("Start date cannot be after end date.")
            elif st.button("Fetch ET and NDVI Data"):
                with st.spinner(f"Fetching data for '{selected_section}'..."):
                    et_df = fetch_et_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)
                    ndvi_df = fetch_ndvi_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)

                    if et_df is not None and ndvi_df is not None:
                        # Merge the two dataframes on their date index
                        combined_df = pd.merge(et_df, ndvi_df, left_index=True, right_index=True)
                        st.session_state[f'openet_{selected_section}'] = combined_df
                    else:
                        st.warning("Could not retrieve complete data from OpenET.")
                        if f'openet_{selected_section}' in st.session_state:
                            del st.session_state[f'openet_{selected_section}']
    
    # --- Plotting and Data Display ---
    if st.session_state.get(f'openet_{selected_section}') is not None:
        st.markdown("---")
        st.subheader(f"OpenET Data for Section: {selected_section}")
        df_to_show = st.session_state[f'openet_{selected_section}']

        # Create the dual-axis plot
        fig, ax1 = plt.subplots(figsize=(12, 6))

        # Plot ET on the primary y-axis (left)
        color = 'tab:blue'
        ax1.set_xlabel('Date')
        ax1.set_ylabel('ET (in)', color=color)
        ax1.plot(df_to_show.index, df_to_show['ET (in)'], color=color, label='ET (in)')
        ax1.tick_params(axis='y', labelcolor=color)

        # Create a second y-axis that shares the same x-axis
        ax2 = ax1.twinx()
        color = 'tab:green'
        ax2.set_ylabel('NDVI', color=color)
        ax2.plot(df_to_show.index, df_to_show['NDVI'], color=color, linestyle='--', label='NDVI')
        ax2.tick_params(axis='y', labelcolor=color)
        
        # Formatting
        ax1.set_title('Daily Evapotranspiration (ET) and NDVI')
        ax1.grid(True)
        fig.tight_layout()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")

        st.pyplot(fig)

        st.markdown("##### Raw Data")
        st.dataframe(df_to_show)

    # --- Other Data Entry Forms ---
    # (This section is unchanged)
    form_key_map = { "Water Usage": "water_form", "Crop Data": "crop_form", "Soil Data": "soil_form", "Fertilizer Data": "fertilizer_form", "Yield Data": "yield_form" }
    fields_map = { "Water Usage": {"date": (st.date_input, ["Date"], {"value": date.today()}), "water_gallons": (st.number_input, ["Water Used (Gallons)"], {"min_value": 0.0, "format": "%.2f"}), "source": (st.selectbox, ["Water Source"], {"options": ["Well", "River", "Canal", "Municipal"]})}, "Crop Data": {"planting_date": (st.date_input, ["Planting Date"], {"value": date.today()}), "crop_type": (st.selectbox, ["Crop Type"], {"options": ["Corn", "Soybeans", "Wheat", "Cotton", "Other"]}), "acres_planted": (st.number_input, ["Acres Planted"], {"min_value": 0.0, "format": "%.2f"})}, "Soil Data": {"sample_date": (st.date_input, ["Sample Date"], {"value": date.today()}), "ph_level": (st.number_input, ["pH Level"], {"min_value": 0.0, "max_value": 14.0, "format": "%.1f"}), "organic_matter": (st.number_input, ["Organic Matter (%)"], {"min_value": 0.0, "format": "%.2f"})}, "Fertilizer Data": {"application_date": (st.date_input, ["Application Date"], {"value": date.today()}), "fertilizer_type": (st.text_input, ["Fertilizer Type"], {}), "amount_applied": (st.number_input, ["Amount Applied (lbs/acre)"], {"min_value": 0.0, "format": "%.2f"})}, "Yield Data": {"harvest_date": (st.date_input, ["Harvest Date"], {"value": date.today()}), "total_yield": (st.number_input, ["Total Yield"], {"min_value": 0.0, "format": "%.2f"}), "units": (st.text_input, ["Units (e.g., bushels)"], {})} }

    if data_type in form_key_map: 
        with st.form(form_key_map[data_type]):
            st.subheader("Data Details")
            columns = st.columns(2)
            field_items = list(fields_map[data_type].items())
            for i, (name, (func, args, kwargs)) in enumerate(field_items):
                with columns[i % 2]:
                    func(*args, **kwargs)
            st.text_area("Notes")
            if st.form_submit_button(f"Submit {data_type}"):
                st.success(f"{data_type} for '{selected_section}' submitted!")
