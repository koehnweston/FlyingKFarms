import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import tempfile
import os
import zipfile

st.set_page_config(page_title="Map View", page_icon="🗺️", layout="wide")

st.markdown("# 🗺️ Map View")
st.sidebar.header("Map View")
st.write(
    """Upload a zipped shapefile (`.zip`) to visualize your farm's fields on a map.
       The map will automatically center on your data."""
)

# --- Shapefile Uploader ---
uploaded_file = st.file_uploader(
    "Choose a zipped shapefile",
    type="zip",
    help="Upload a .zip file containing all shapefile components (.shp, .shx, .dbf, etc.)"
)

# --- Map Display ---
# Create a default map centered on the US
m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

if uploaded_file is not None:
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Unzip the uploaded file
            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the .shp file in the extracted contents
            shp_file_path = None
            for file in os.listdir(temp_dir):
                if file.endswith(".shp"):
                    shp_file_path = os.path.join(temp_dir, file)
                    break

            if shp_file_path:
                # Read the shapefile with geopandas
                gdf = gpd.read_file(shp_file_path)

                # Reproject to WGS84 (EPSG:4326) if not already
                if gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(epsg=4326)

                # Add the GeoDataFrame to the map
                folium.GeoJson(gdf, tooltip=folium.GeoJsonTooltip(fields=list(gdf.columns))).add_to(m)

                # Get the bounds of the GeoDataFrame to center the map
                bounds = gdf.total_bounds
                m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
                st.success("Shapefile loaded and displayed on the map!")
            else:
                st.error("No .shp file found in the uploaded zip archive.")

    except Exception as e:
        st.error(f"An error occurred while processing the file: {e}")

# Display the map
st_folium(m, width='100%', height=600)
