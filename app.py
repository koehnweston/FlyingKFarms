import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
import io
import requests
from datetime import date
import tempfile
import os
import folium
from streamlit_folium import st_folium

# --- Page Configuration ---
# Set the layout to wide for better form visibility
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

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
        
        # --- IMPORTANT: Re-project to standard web mapping CRS (WGS 84) ---
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


# --- Main App ---
st.markdown("# 🌾 Farming Data Entry")

# --- Sidebar ---
st.sidebar.header("Field Setup")
st.sidebar.info(
    "Field data is automatically loaded from the `parcels_2.zip` file in the GitHub repository."
)

if st.sidebar.button("Clear Cache & Reload Data"):
    st.cache_data.clear()
    st.session_state.data_loaded = False
    st.rerun()

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.gdf = None
    st.session_state.field_options = []

if not st.session_state.data_loaded:
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
                st.sidebar.success(f"Shapefile loaded! Found {len(st.session_state.field_options)} unique sections.")
            else:
                st.sidebar.error("Shapefile is missing the required 'Section' column.")
                st.sidebar.warning(f"Columns found: {gdf.columns.tolist()}")
                st.session_state.field_options = []
        else:
            st.sidebar.error("Failed to load shapefile from GitHub. Please check the URL and file format.")
    st.session_state.data_loaded = True


# --- Data Entry Section ---
if not st.session_state.field_options:
    st.warning("Could not load field data. Please check the configuration in the sidebar.")
else:
    data_type = st.selectbox(
        "Select Data Type to Enter",
        ["Water Usage", "Crop Data", "Soil Data", "Fertilizer Data", "Yield Data"]
    )

    st.markdown("---")
    
    # --- Field Selection and Map (Moved outside the form) ---
    st.subheader("Field Information")
    selected_section = st.selectbox("Select Field Section", options=st.session_state.field_options, index=0)

    if selected_section and st.session_state.gdf is not None:
        section_data = st.session_state.gdf[st.session_state.gdf["Section"] == selected_section].iloc[0]
        
        # Display Metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("X Coordinate", f"{section_data.get('X', 'N/A'):.4f}" if isinstance(section_data.get('X'), (int, float)) else "N/A")
        with col2:
            st.metric("Y Coordinate", f"{section_data.get('Y', 'N/A'):.4f}" if isinstance(section_data.get('Y'), (int, float)) else "N/A")
        with col3:
            st.metric("Area", f"{section_data.get('Area', 'N/A'):.2f}" if isinstance(section_data.get('Area'), (int, float)) else "N/A")

        # Interactive Map
        st.markdown("##### Field Map")
        map_center = [section_data.geometry.centroid.y, section_data.geometry.centroid.x]
        m = folium.Map(location=map_center, zoom_start=15)

        folium.TileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Esri Satellite',
            overlay=False,
            control=True
        ).add_to(m)
        
        folium.GeoJson(
            section_data.geometry,
            style_function=lambda x: {'fillColor': 'cyan', 'color': 'blue', 'weight': 2.5, 'fillOpacity': 0.4}
        ).add_to(m)
        
        st_folium(m, key=selected_section, width=725, height=500)

    # --- Data Entry Form ---
    st.markdown(f"### Enter {data_type}")
    
    def data_entry_form(form_key, fields):
        with st.form(form_key):
            st.subheader("Data Details")
            form_inputs = {}
            columns = st.columns(2)
            for i, (name, (func, args, kwargs)) in enumerate(fields.items()):
                with columns[i % 2]:
                    form_inputs[name] = func(*args, **kwargs)

            notes = st.text_area("Notes")
            
            submitted = st.form_submit_button(f"Submit {data_type}")
            if submitted:
                # 'selected_section' is accessible here because it's defined outside the form
                st.success(f"{data_type} for section '{selected_section}' submitted successfully!")

    # --- Define and Render Forms ---
    if data_type == "Water Usage":
        fields = {
            "date": (st.date_input, ["Date"], {"value": date.today()}),
            "water_gallons": (st.number_input, ["Water Used (Gallons)"], {"min_value": 0.0, "format": "%.2f"}),
            "source": (st.selectbox, ["Water Source"], {"options": ["Well", "River", "Canal", "Municipal"]})
        }
        data_entry_form("water_form", fields)

    elif data_type == "Crop Data":
        fields = {
            "planting_date": (st.date_input, ["Planting Date"], {"value": date.today()}),
            "crop_type": (st.selectbox, ["Crop Type"], {"options": ["Corn", "Soybeans", "Wheat", "Cotton", "Other"]}),
            "acres_planted": (st.number_input, ["Acres Planted"], {"min_value": 0.0, "format": "%.2f"})
        }
        data_entry_form("crop_form", fields)

    elif data_type == "Soil Data":
        fields = {
            "sample_date": (st.date_input, ["Sample Date"], {"value": date.today()}),
            "ph_level": (st.number_input, ["pH Level"], {"min_value": 0.0, "max_value": 14.0, "step": 0.1, "format": "%.1f"}),
            "organic_matter": (st.number_input, ["Organic Matter (%)"], {"min_value": 0.0, "max_value": 100.0, "format": "%.2f"})
        }
        data_entry_form("soil_form", fields)
        
    elif data_type == "Fertilizer Data":
        fields = {
            "application_date": (st.date_input, ["Application Date"], {"value": date.today()}),
            "fertilizer_type": (st.text_input, ["Fertilizer Type (e.g., N-P-K)"], {}),
            "amount_applied": (st.number_input, ["Amount Applied (lbs/acre)"], {"min_value": 0.0, "format": "%.2f"})
        }
        data_entry_form("fertilizer_form", fields)

    elif data_type == "Yield Data":
        fields = {
            "harvest_date": (st.date_input, ["Harvest Date"], {"value": date.today()}),
            "total_yield": (st.number_input, ["Total Yield"], {"min_value": 0.0, "format": "%.2f"}),
            "units": (st.text_input, ["Units (e.g., bushels, lbs, tons)"], {})
        }
        data_entry_form("yield_form", fields)

