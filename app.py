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

# --- Page Configuration ---
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

# --- API Key Configuration ---
# Ensure you have OPENET_API_KEY in your Streamlit secrets
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
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data from URL: {e}")
        return None
    except Exception as e:
        st.error(f"Error reading shapefile: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@st.cache_data
def fetch_openet_data(_geometry, start_date, end_date, api_key):
    """
    Fetches time series data from the OpenET API for a single point (centroid)
    using the /raster/timeseries/point endpoint.
    """
    API_URL = "https://openet-api.org/raster/timeseries/point"
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    
    payload = {
        "date_range": [
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        ],
        "file_format": "JSON",
        "geometry": [
            _geometry.centroid.x,  # Longitude
            _geometry.centroid.y   # Latitude
        ],
        "interval": "daily",
        "model": "Ensemble",
        "reference_et": "gridMET",
        "units": "in",
        "variable": "ET"
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        
        # OpenET API returns a 'time' column
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        
        # The ET variable is returned in a column named 'et'
        df.rename(columns={'et': 'ET (in)'}, inplace=True)
        
        return df[['ET (in)']]
        
    except requests.exceptions.RequestException as e:
        st.error(f"OpenET API Error: {e}")
        if e.response:
            st.error(f"Status Code: {e.response.status_code}")
            try:
                st.json(e.response.json())
            except json.JSONDecodeError:
                st.text(e.response.text)
        return None

# --- Main App ---
st.markdown("# 🌾 Farming Data Entry")

# --- Sidebar ---
st.sidebar.header("Field Setup")
st.sidebar.info("Field data is automatically loaded from GitHub.")

if st.sidebar.button("Clear Cache & Reload Data"):
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()

# --- Data Loading Logic ---
if 'data_loaded' not in st.session_state:
    with st.spinner("Loading field data from GitHub..."):
        gdf = load_data_from_github(SHAPEFILE_URL)
        if gdf is not None:
            # Standardize column names for 'Section' and 'Area'
            column_map = {col.lower(): col for col in gdf.columns}
            if 'section' in column_map:
                gdf.rename(columns={column_map['section']: 'Section'}, inplace=True)
            if 'area' in column_map:
                gdf.rename(columns={column_map['area']: 'Area'}, inplace=True)

            # Calculate centroids for display
            if 'geometry' in gdf.columns and not gdf.empty:
                centroids = gdf.geometry.centroid
                gdf['X'] = centroids.x
                gdf['Y'] = centroids.y
            
            st.session_state.gdf = gdf
            
            # Populate field options for the dropdown
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
    # This is the only data type now, so the dropdown is removed.
    data_type = "OpenET Data"
    
    st.subheader("Field Information")
    selected_section = st.selectbox("Select Field Section", options=st.session_state.field_options, index=0)

    if selected_section and 'gdf' in st.session_state and st.session_state.gdf is not None:
        section_data = st.session_state.gdf[st.session_state.gdf["Section"] == selected_section].iloc[0]
        
        # Display field metrics and map
        col1, col2, col3 = st.columns(3)
        col1.metric("X (Longitude)", f"{section_data.get('X', 0):.4f}")
        col2.metric("Y (Latitude)", f"{section_data.get('Y', 0):.4f}")
        col3.metric("Area", f"{section_data.get('Area', 0):.2f}")

        st.markdown("##### Field Map")
        map_center = [section_data.geometry.centroid.y, section_data.geometry.centroid.x]
        m = folium.Map(location=map_center, zoom_start=15, tiles=None)
        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Esri Satellite').add_to(m)
        folium.GeoJson(section_data.geometry, style_function=lambda x: {'fillColor': 'cyan', 'color': 'blue', 'weight': 2.5, 'fillOpacity': 0.4}).add_to(m)
        st_folium(m, key=selected_section, width=725, height=500)

    st.markdown("---")
    st.markdown(f"### Fetch {data_type}")

    # --- OpenET Data Section ---
    if not OPENET_API_KEY:
        st.error("OpenET API key not configured.")
        st.info("""
            To use this feature, add your OpenET API key to Streamlit's secrets.
            1. Go to your app's dashboard on Streamlit Community Cloud.
            2. Click on 'Settings' > 'Secrets'.
            3. Add a secret with the key `OPENET_API_KEY` and your API token as the value.
            For example: `OPENET_API_KEY = "your-key-here"`
        """)
    else:
        # Date range selection
        today = date.today()
        one_year_ago = today - timedelta(days=365)
        dcol1, dcol2 = st.columns(2)
        start_date = dcol1.date_input("Start Date", one_year_ago)
        end_date = dcol2.date_input("End Date", today)

        # Fetch button and logic
        if start_date > end_date:
            st.warning("Start date cannot be after end date.")
        elif st.button("Fetch OpenET Data"):
            with st.spinner(f"Fetching OpenET data for '{selected_section}'..."):
                openet_df = fetch_openet_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)
                if openet_df is not None and not openet_df.empty:
                    st.session_state[f'openet_{selected_section}'] = openet_df
                else:
                    st.warning("No data returned from OpenET. This could be due to the date range or API issues.")
                    if f'openet_{selected_section}' in st.session_state:
                        del st.session_state[f'openet_{selected_section}']
    
    # Display fetched OpenET data if it exists in the session state
    if st.session_state.get(f'openet_{selected_section}') is not None:
        st.markdown("---")
        st.subheader(f"OpenET Data for Section: {selected_section}")
        df_to_show = st.session_state[f'openet_{selected_section}']
        
        st.markdown("##### Evapotranspiration (ET)")
        st.line_chart(df_to_show['ET (in)'])
        
        st.markdown("##### Raw Data")
        st.dataframe(df_to_show)
