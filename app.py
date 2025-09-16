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
import numpy as np

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
def fetch_openet_variable(
    _section_name, _geometry, start_date, end_date, api_key, variable, new_column_name, model="Ensemble", units=None
):
    """
    Generic function to fetch a time series variable from the OpenET API.
    _section_name is unused but vital for Streamlit's cache to work correctly.
    """
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": api_key,
    }
    coords = _geometry.exterior.coords
    geometry_list = [val for pair in coords for val in pair]

    payload = {
        "date_range": [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
        "geometry": geometry_list,
        "model": model,
        "variable": variable,
        "reference_et": "gridMET",
        "interval": "daily",
        "reducer": "mean",
        "file_format": "JSON",
    }
    if units:
        payload["units"] = units

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        
        if df.empty:
            return None
            
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        df.rename(columns={variable.lower(): new_column_name}, inplace=True)

        if variable == 'ndvi':
            df[new_column_name] = df[new_column_name].interpolate(method='linear')
            
        return df[[new_column_name]]
        
    except requests.exceptions.RequestException as e:
        handle_api_error(e)
        return None

def run_irrigation_simulation(df):
    """
    Simulates daily plant available water and irrigation based on a set of rules.
    """
    # --- Model Parameters ---
    MAX_PAW = 6.0  # inches, equivalent to Field Capacity
    IRRIGATION_TRIGGER_LEVEL = 3*MAX_PAW / 5  # inches
    MAX_DAILY_IRRIGATION = 0.25  # inches

    sim_df = df.copy()
    
    # --- FIX: Fill potential missing values in the columns before the loop ---
    sim_df['ET (in)'] = sim_df['ET (in)'].fillna(0)
    sim_df['Precipitation (in)'] = sim_df['Precipitation (in)'].fillna(0)

    # --- Initialize simulation columns ---
    sim_df['Plant Available Water (in)'] = MAX_PAW
    sim_df['Irrigation Applied (in)'] = 0.0

    # --- Loop through each day of the dataset ---
    for i in range(1, len(sim_df)):
        prev_paw = sim_df.iloc[i-1]['Plant Available Water (in)']
        
        current_date = sim_df.index[i]
        # --- FIX: Removed .fillna(0) from these lines ---
        daily_et = sim_df.iloc[i]['ET (in)']
        daily_precip = sim_df.iloc[i]['Precipitation (in)']

        # --- Determine if today is in the pumping season (May 25 - Sep 20) ---
        is_in_season = (5, 25) <= (current_date.month, current_date.day) <= (9, 20)

        # --- Reset PAW to max on the first day of the season each year ---
        prev_date = sim_df.index[i-1]
        is_prev_day_in_season = (5, 25) <= (prev_date.month, prev_date.day) <= (9, 20)
        if is_in_season and not is_prev_day_in_season:
             prev_paw = MAX_PAW

        # --- Calculate water balance before considering irrigation ---
        current_paw = prev_paw - daily_et + daily_precip
        
        irrigation_today = 0.0
        if is_in_season:
            # --- Trigger irrigation if PAW is at or below the threshold ---
            if current_paw <= IRRIGATION_TRIGGER_LEVEL:
                needed_water = MAX_PAW - current_paw
                irrigation_today = min(needed_water, MAX_DAILY_IRRIGATION)

        # --- Update final PAW for the day, clamping between 0 and MAX_PAW ---
        final_paw = max(0, min(current_paw + irrigation_today, MAX_PAW))

        # --- Store results for the current day ---
        sim_df.iloc[i, sim_df.columns.get_loc('Plant Available Water (in)')] = final_paw
        sim_df.iloc[i, sim_df.columns.get_loc('Irrigation Applied (in)')] = irrigation_today
        
    # --- Calculate cumulative consumed groundwater (total irrigation) ---
    sim_df['Consumed Groundwater (in)'] = sim_df['Irrigation Applied (in)'].cumsum()
    return sim_df

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
    st.markdown("### Fetch OpenET Data (ET, NDVI, & Precipitation)")

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
        elif st.button("Fetch ET, NDVI, and Precipitation Data"):
            with st.spinner(f"Fetching OpenET data for '{selected_section}'..."):
                et_df = fetch_openet_variable(
                    selected_section, section_data.geometry, start_date, end_date, OPENET_API_KEY,
                    variable="ET", new_column_name="ET (in)", units="in"
                )
                ndvi_df = fetch_openet_variable(
                    selected_section, section_data.geometry, start_date, end_date, OPENET_API_KEY,
                    variable="ndvi", new_column_name="NDVI", model="ssebop"
                )
                precip_df = fetch_openet_variable(
                    selected_section, section_data.geometry, start_date, end_date, OPENET_API_KEY,
                    variable="pr", new_column_name="Precipitation (in)", units="in"
                )

                session_key = f'data_{selected_section}'
                if session_key in st.session_state:
                    del st.session_state[session_key]
                
                data_frames = [df for df in [et_df, ndvi_df, precip_df] if df is not None]
                
                if data_frames:
                    combined_df = data_frames[0]
                    for df in data_frames[1:]:
                        combined_df = pd.merge(combined_df, df, left_index=True, right_index=True, how='outer')
                    
                    st.session_state[session_key] = combined_df
                    st.success("Successfully fetched and combined all available data!")
                else:
                    st.warning("No data returned from OpenET for any variable.")

    session_key = f'data_{selected_section}'
    if st.session_state.get(session_key) is not None:
        st.markdown("---")
        st.subheader(f"Data & Irrigation Simulation for Section: {selected_section}")
        df_to_show = st.session_state[session_key].copy()

        # --- RUN AND DISPLAY IRRIGATION SIMULATION ---
        if 'ET (in)' in df_to_show.columns and 'Precipitation (in)' in df_to_show.columns:
            
            # Run the simulation
            simulated_df = run_irrigation_simulation(df_to_show)
            
            st.markdown("##### Daily Plant Available Water (PAW)")
            st.info("Simulation assumes a max PAW of 6 inches. Irrigation is triggered when PAW drops to 3 inches.")
            st.line_chart(simulated_df['Plant Available Water (in)'])

            st.markdown("##### Simulated Consumed Groundwater (Cumulative Irrigation)")
            st.info("Irrigation is limited to a maximum of 0.25 inches per day and only occurs between May 25 and Sep 20.")
            st.line_chart(simulated_df['Consumed Groundwater (in)'])
            
            # Add simulation results to the main dataframe for the table view
            df_to_show = simulated_df.copy()
        
        else:
             st.warning("ET and/or Precipitation data is missing. Cannot run irrigation simulation.")
             if 'NDVI' in df_to_show.columns:
                st.markdown("##### Daily NDVI")
                st.line_chart(df_to_show['NDVI'])

        st.markdown("---")
        st.markdown("##### Raw Data Table (with simulation results)")
        st.dataframe(df_to_show)
