import streamlit as st

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.markdown("# ⚙️ Settings")
st.sidebar.header("Settings")
st.write("Configure application settings and preferences here.")

st.subheader("Units")
unit_system = st.radio(
    "Select Unit System",
    ('Imperial (acres, gallons, lbs)', 'Metric (hectares, liters, kg)')
)

st.subheader("API Keys")
st.info("In the future, you can add fields here for climate data APIs, etc.")
climate_api_key = st.text_input("Climate Data API Key", type="password")

st.subheader("Data Management")
st.button("Export All Data")
st.button("Import Data from File")
