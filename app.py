import streamlit as st
import pandas as pd
import geopandas as gpd
import zipfile
import io
import requests
from datetime import date

# --- Page Configuration ---
# Set the layout to wide for better form visibility
st.set_page_config(page_title="Farming Data Entry", page_icon="🌾", layout="wide")

# --- Data Loading ---
# This is the direct raw URL to your file on GitHub
SHAPEFILE_URL = "https://raw.githubusercontent.com/koehnweston/FlyingKFarms/main/parcels_2.zip"

@st.cache_data
def load_data_from_github(url):
    """Loads a zipped shapefile from a GitHub raw URL."""
    try:
        response = requests.get(url)
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()
        
        # Read the content into an in-memory buffer
        buffer = io.BytesIO(response.content)
        
        # Geopandas can read a zip file directly from a file-like object
        gdf = gpd.read_file(buffer)
        return gdf
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data from URL: {e}")
        return None
    except Exception as e:
        st.error(f"Error reading shapefile: {e}")
        return None


# --- Main App ---
st.markdown("# 🌾 Farming Data Entry")

# --- Sidebar for File Upload and Instructions ---
st.sidebar.header("Field Setup")
st.sidebar.info(
    "Field data is automatically loaded from the `parcels_2.zip` file in the GitHub repository."
)

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
                st.sidebar.error("Shapefile is missing the required 'Section' column.")
                st.session_state.field_options = []
        else:
            st.sidebar.error("Failed to load shapefile from GitHub. Please check the URL and file format.")
    st.session_state.data_loaded = True


# --- Data Entry Section ---
# Only show the data entry options if a valid shapefile has been loaded
if not st.session_state.field_options:
    st.warning("Could not load field data. Please check the configuration.")
else:
    data_type = st.selectbox(
        "Select Data Type to Enter",
        ["Water Usage", "Crop Data", "Soil Data", "Fertilizer Data", "Yield Data"]
    )

    st.markdown("---")
    st.markdown(f"### Enter {data_type}")

    # --- Reusable Form Component ---
    # We create a function to avoid repeating the form logic
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
                # Example of data to be saved:
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

