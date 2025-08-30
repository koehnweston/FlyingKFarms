import streamlit as st

st.set_page_config(
    page_title="Agri-Producer Home",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🌱 Agri-Producer Data Management Framework")

st.sidebar.success("Select a page above.")

st.markdown(
    """
    ### Welcome to your agricultural data management application!

    This application is a framework to help you integrate and analyze various data sources for your farm.

    **Select a page from the sidebar to get started:**

    - **Dashboard:** Get a high-level overview of your operations.
    - **Map View:** Upload shapefiles and visualize your fields.
    - **Data Entry:** Manually input data for crops, water, soil, etc.
    - **Data Analysis:** Explore relationships within your data.
    - **Settings:** Configure application settings.

    This is a starting framework. You can build upon this structure to add more complex features,
    connect to databases, and perform detailed analyses. The code is organized for easy extension.
"""
)
