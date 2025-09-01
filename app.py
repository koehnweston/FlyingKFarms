import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
import io
import requests
from datetime import date
import tempfile
import os

# --- Page Configuration ---
# Set the layout to wide for better form visibility
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

# --- Data Loading ---
# This is the direct raw URL to your file on GitHub
SHAPEFILE_URL = "https://raw.githubusercontent.com/koehnweston/FlyingKFarms/main/parcels_2.zip"

@st.cache_data
def load_data_from_github(url):
    """
    Loads a zipped shapefile from a GitHub raw URL.
    This version dynamically finds the .shp file within the zip archive.
    """
    tmp_path = None
    try:
        response = requests.get(url)
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        
        # Create a temporary file to save the zip content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        # NEW: Inspect the zip file to find the shapefile name dynamically
        with zipfile.ZipFile(tmp_path, 'r') as zf:
            # Find the first file ending with .shp (case-insensitive)
            shapefile_name = next((name for name in zf.namelist() if name.lower().endswith('.shp')), None)
            
            if not shapefile_name:
                st.error("Error: No .shp file found inside the zip archive.")
                return None
        
        # Construct the specific URI for geopandas to read the file from within the zip
        # The syntax is "zip://path/to/file.zip!layer_name"
        # The layer_name is the shapefile name itself (e.g., 'Parcels_2.shp')
        uri = f"zip://{tmp_path}!{shapefile_name}"
        gdf = gpd.read_file(uri)
        return gdf
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data from URL: {e}")
        return None
    except Exception as e:
        st.error(f"Error reading shapefile: {e}")
        return None
    finally:
        # Clean up the temporary file
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# --- Main App ---
st.markdown("# 🌾 Farming Data Entry")

# --- Sidebar ---
st.sidebar.header("Field Setup")
st.sidebar.info(
    "Field data is automatically loaded from the `parcels_2.zip` file in the GitHub repository."
)

# Add a button to clear the cache and rerun the data loading
if st.sidebar.button("Clear Cache & Reload Data"):
    st.cache_data.clear()
    st.session_state.data_loaded = False
    st.rerun()

# Initialize session state if not already done
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.gdf = None
    st.session_state.field_options = []

# Load data only once
if not st.session_state.data_loaded:
    with st.spinner("Loading field data from GitHub..."):
        gdf = load_data_from_github(SHAPEFILE_URL)
        if gdf is not None:
            st.session_state.gdf = gdf
            # Check for the required 'Section' column
            if "Section" in gdf.columns:
                # Get unique, sorted list of sections
                st.session_state.field_options = sorted(gdf["Section"].unique().tolist())
                st.sidebar.success(f"Shapefile loaded! Found {len(st.session_state.field_options)} unique sections.")
            else:
                # ENHANCED ERROR: Show which columns were found
                st.sidebar.error("Shapefile is missing the required 'Section' column.")
                st.sidebar.warning(f"Columns found: {gdf.columns.tolist()}")
                st.session_state.field_options = []
        else:
            st.sidebar.error("Failed to load shapefile from GitHub. Please check the URL and file format.")
    st.session_state.data_loaded = True


# --- Data Entry Section ---
# Only show the data entry options if a valid shapefile has been loaded
if not st.session_state.field_options:
    st.warning("Could not load field data. Please check the configuration in the sidebar.")
else:
    data_type = st.selectbox(
        "Select Data Type to Enter",
        ["Water Usage", "Crop Data", "Soil Data", "Fertilizer Data", "Yield Data"]
    )

    st.markdown("---")
    st.markdown(f"### Enter {data_type}")

    # --- Reusable Form Component ---
    def data_entry_form(form_key, fields):
        with st.form(form_key):
            # First, create the section selector and display its info
            st.subheader("Field Information")
            selected_section = st.selectbox("Select Field Section", options=st.session_state.field_options, index=0)

            # Display X, Y, and Area for the selected section
            if selected_section:
                section_data = st.session_state.gdf[st.session_state.gdf["Section"] == selected_section].iloc[0]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("X Coordinate", f"{section_data.get('X', 'N/A'):.2f}" if isinstance(section_data.get('X'), (int, float)) else "N/A")
                with col2:
                    st.metric("Y Coordinate", f"{section_data.get('Y', 'N/A'):.2f}" if isinstance(section_data.get('Y'), (int, float)) else "N/A")
                with col3:
                    st.metric("Area", f"{section_data.get('Area', 'N/A'):.2f}" if isinstance(section_data.get('Area'), (int, float)) else "N/A")
            
            st.subheader("Data Details")
            # Create input fields based on the provided dictionary
            form_inputs = {}
            columns = st.columns(2)
            for i, (name, (func, args, kwargs)) in enumerate(fields.items()):
                with columns[i % 2]:
                    form_inputs[name] = func(*args, **kwargs)

            # Text area for notes is common to all forms
            notes = st.text_area("Notes")
            
            submitted = st.form_submit_button(f"Submit {data_type}")
            if submitted:
                st.success(f"{data_type} for section '{selected_section}' submitted successfully!")
                # In a real app, you would save this data to a database.
                # data_to_save = {"section": selected_section, "notes": notes, **form_inputs}
                # st.write(data_to_save)


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

