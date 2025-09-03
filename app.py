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
# Set the layout to wide for better form visibility
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

# --- API Key Configuration ---
OPENET_API_KEY = st.secrets.get("OPENET_API_KEY")

# --- Data Loading ---
# This is the direct raw URL to your file on GitHub
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
        
        # FIX: Manually assign the known source CRS if it's missing
        if gdf.crs is None:
            st.info("Shapefile CRS not found. Assuming KS State Plane North (EPSG:2241).")
            gdf.set_crs(epsg=2241, inplace=True)
        
        # Convert from State Plane to the latitude/longitude the API needs
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
    Fetches time series data from the OpenET API for a given geometry.
    """
    API_URL = "https://openet-api.org/v2/timeseries/geometry"
    headers = {
        "Content-Type": "application/json",
        "Authorization": api_key
    }
    geom_geojson = _geometry.__geo_interface__
    
    payload = {
        "geometry": geom_geojson,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "model": "ensemble",
        "variable": ["et", "ndvi"],
        "output_format": "csv"
    }

    if st.session_state.get("debug_mode", False):
        st.sidebar.subheader("API Request Payload")
        st.sidebar.json(payload)

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        df = pd.read_csv(io.StringIO(response.text))
        df['date'] = pd.to_datetime(df['time'])
        df.set_index('date', inplace=True)
        
        rename_map = {col: 'ET (mm)' for col in df.columns if 'et_ensemble' in col}
        rename_map.update({col: 'NDVI' for col in df.columns if 'ndvi_ensemble' in col})
        df.rename(columns=rename_map, inplace=True)
        
        return df[['ET (mm)', 'NDVI']]
        
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 404:
            st.error("OpenET API Error: 404 Not Found.")
            st.warning("""
                This can occur for a few reasons:
                1.  **Location:** The selected field might be outside OpenET's coverage area.
                2.  **API Key:** The API key in your Streamlit secrets might be invalid or expired. Please double-check it.
                3.  **Request Format:** There might be an issue with the data sent.
                
                Enable "Debug Mode" in the sidebar to view the exact data payload sent to the API.
            """)
        else:
            st.error(f"OpenET API Error: {e}")
            st.error(f"Response content: {e.response.text if e.response else 'No response'}")
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

    if data_type == "OpenET Data":
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
            today = date.today()
            one_year_ago = today - timedelta(days=365)
            dcol1, dcol2 = st.columns(2)
            start_date = dcol1.date_input("Start Date", one_year_ago)
            end_date = dcol2.date_input("End Date", today)

            if start_date > end_date:
                st.warning("Start date cannot be after end date.")
            elif st.button("Fetch OpenET Data"):
                with st.spinner(f"Fetching OpenET data for '{selected_section}'..."):
                    openet_df = fetch_openet_data(section_data.geometry, start_date, end_date, OPENET_API_KEY)
                    if openet_df is not None and not openet_df.empty:
                        st.session_state[f'openet_{selected_section}'] = openet_df
                    else:
                        st.warning("No data returned from OpenET.")
                        if f'openet_{selected_section}' in st.session_state:
                            del st.session_state[f'openet_{selected_section}']
    
    if st.session_state.get(f'openet_{selected_section}') is not None:
        st.markdown("---")
        st.subheader(f"OpenET Data for Section: {selected_section}")
        df_to_show = st.session_state[f'openet_{selected_section}']
        st.markdown("##### Evapotranspiration (ET)")
        st.line_chart(df_to_show['ET (mm)'])
        st.markdown("##### Normalized Difference Vegetation Index (NDVI)")
        st.line_chart(df_to_show['NDVI'])
        st.markdown("##### Raw Data")
        st.dataframe(df_to_show)

    elif data_type in form_key_map: # Handle all other data entry forms
        form_key_map = {
            "Water Usage": "water_form", "Crop Data": "crop_form",
            "Soil Data": "soil_form", "Fertilizer Data": "fertilizer_form",
            "Yield Data": "yield_form"
        }
        
        fields_map = {
            "Water Usage": {"date": (st.date_input, ["Date"], {"value": date.today()}), "water_gallons": (st.number_input, ["Water Used (Gallons)"], {"min_value": 0.0, "format": "%.2f"}), "source": (st.selectbox, ["Water Source"], {"options": ["Well", "River", "Canal", "Municipal"]})},
            "Crop Data": {"planting_date": (st.date_input, ["Planting Date"], {"value": date.today()}), "crop_type": (st.selectbox, ["Crop Type"], {"options": ["Corn", "Soybeans", "Wheat", "Cotton", "Other"]}), "acres_planted": (st.number_input, ["Acres Planted"], {"min_value": 0.0, "format": "%.2f"})},
            "Soil Data": {"sample_date": (st.date_input, ["Sample Date"], {"value": date.today()}), "ph_level": (st.number_input, ["pH Level"], {"min_value": 0.0, "max_value": 14.0, "format": "%.1f"}), "organic_matter": (st.number_input, ["Organic Matter (%)"], {"min_value": 0.0, "format": "%.2f"})},
            "Fertilizer Data": {"application_date": (st.date_input, ["Application Date"], {"value": date.today()}), "fertilizer_type": (st.text_input, ["Fertilizer Type"], {}), "amount_applied": (st.number_input, ["Amount Applied (lbs/acre)"], {"min_value": 0.0, "format": "%.2f"})},
            "Yield Data": {"harvest_date": (st.date_input, ["Harvest Date"], {"value": date.today()}), "total_yield": (st.number_input, ["Total Yield"], {"min_value": 0.0, "format": "%.2f"}), "units": (st.text_input, ["Units (e.g., bushels)"], {})}
        }
        
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
