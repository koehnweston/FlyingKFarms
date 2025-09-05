import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
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
API_URL = "https://openet-api.org/raster/timeseries/polygon"

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

def handle_api_error(e):
    """Helper function to display API errors in Streamlit."""
    st.error(f"OpenET API Error: {e}")
    if e.response:
        st.error(f"Status Code: {e.response.status_code}")
        try:
            st.json(e.response.json())
        except json.JSONDecodeError:
            st.text(e.response.text)

@st.cache_data
def fetch_openet_data(_geometry, start_date, end_date, api_key):
    """
    Fetches daily Evapotranspiration (ET) time series data from the OpenET API.
    """
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    coords = _geometry.exterior.coords
    geometry_list = [val for pair in coords for val in pair]

    payload = {
        "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
        "geometry": geometry_list,
        "model": "Ensemble",
        "variable": "ET",
        "reference_et": "gridMET",
        "interval": "daily",
        "reducer": "mean",
        "units": "in",
        "file_format": "JSON"
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        
        if df.empty:
            return None
        
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        df.rename(columns={'et': 'ET (in)'}, inplace=True)
        
        return df[['ET (in)']]
        
    except requests.exceptions.RequestException as e:
        handle_api_error(e)
        return None

# --- NEW FUNCTION FOR NDVI ---
@st.cache_data
def fetch_ndvi_data(_geometry, start_date, end_date, api_key):
    """
    Fetches daily Normalized Difference Vegetation Index (NDVI) time series from the OpenET API.
    """
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    coords = _geometry.exterior.coords
    geometry_list = [val for pair in coords for val in pair]
    
    payload = {
        "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
        "geometry": geometry_list,
        "model": "ssebop",          # SSEBOP is a common and reliable model for NDVI
        "variable": "ndvi",
        "reference_et": "gridMET",  # This field is required by the API, even for NDVI
        "interval": "daily",
        "reducer": "mean",
        "file_format": "JSON"       # NDVI is unitless, so 'units' key is omitted
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        
        if df.empty:
            return None
        
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        df.rename(columns={'ndvi': 'NDVI'}, inplace=True)
        
        # NDVI values can sometimes be null if there's cloud cover, etc.
        # We fill them forward to have a more continuous line chart.
        df['NDVI'] = df['NDVI'].interpolate(method='linear')

        return df[['NDVI']]
        
    except requests.exceptions.RequestException as e:
        handle_api_error(e)
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
    st.subheader("Field Information")
    selected_section = st.selectbox("Select Field Section", options=st.session_state.field_options, index=0)

    if selected_section and 'gdf' in st.session_state and st.session_state.gdf is not None:
        section_data = st.session_state.gdf[st.session_state.gdf["Section"] == selected_section].iloc[0]
        
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
    st.markdown("### Fetch OpenET Data (ET & NDVI)")

    if not OPENET_API_KEY:
        st.error("OpenET API key not configured.")
        st.info("""
            To use this feature, add your OpenET API key to Streamlit's secrets.
            For example: `OPENET_API_KEY = "your-key-here"`
        """)
    else:
        today = date.today()
        one_year_ago = today - timedelta(days=365)
        dcol1, dcol2 = st.columns(2)
        start_date = dcol1.date_input("Start Date", one_year_ago)
        end_date = dcol2.date_input("End Date", today)

        if start_date > end_date:
            st.warning("Start date cannot be after end date.")
        elif st.button("Fetch ET and NDVI Data"):
            with st.spinner(f"Fetching OpenET data for '{selected_section}'..."):
                # Fetch both datasets
                et_df = fetch_openet_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)
                ndvi_df = fetch_ndvi_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)

                # Clear previous data
                session_key = f'data_{selected_section}'
                if session_key in st.session_state:
                    del st.session_state[session_key]
                
                # Merge if both are available
                if et_df is not None and ndvi_df is not None:
                    # Merge the two dataframes on their common date index
                    combined_df = pd.merge(et_df, ndvi_df, left_index=True, right_index=True, how='outer')
                    st.session_state[session_key] = combined_df
                    st.success("Successfully fetched and combined ET and NDVI data!")
                elif et_df is not None:
                    st.session_state[session_key] = et_df
                    st.info("Fetched ET data, but NDVI was unavailable.")
                elif ndvi_df is not None:
                    st.session_state[session_key] = ndvi_df
                    st.info("Fetched NDVI data, but ET was unavailable.")
                else:
                    st.warning("No data returned from OpenET for either ET or NDVI. This could be due to the date range or API issues.")

    # --- UPDATED DISPLAY SECTION ---
    # Display fetched data if it exists in the session state
    session_key = f'data_{selected_section}'
    if st.session_state.get(session_key) is not None:
        st.markdown("---")
        st.subheader(f"OpenET Data for Section: {selected_section}")
        df_to_show = st.session_state[session_key]

        # Define columns for charts
        plot1, plot2, plot3 = st.columns(3)

        # Plot ET if available
        if 'ET (in)' in df_to_show.columns:
            with plot1:
                st.markdown("##### Daily Evapotranspiration (ET)")
                st.line_chart(df_to_show['ET (in)'])
            
            # Calculate and plot Cumulative ET
            df_to_show['Cumulative ET (in)'] = df_to_show['ET (in)'].cumsum()
            with plot3:
                st.markdown("##### Cumulative Water Use (ET)")
                st.line_chart(df_to_show['Cumulative ET (in)'])
        else:
            plot1.info("ET data not available.")
            plot3.info("Cumulative ET not available.")
        
        # Plot NDVI if available
        if 'NDVI' in df_to_show.columns:
            with plot2:
                st.markdown("##### Daily NDVI")
                st.line_chart(df_to_show['NDVI'])
        else:
            plot2.info("NDVI data not available.")

        st.markdown("##### Raw Data")
        st.dataframe(df_to_show)
