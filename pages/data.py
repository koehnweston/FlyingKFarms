import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(page_title="Data Entry", page_icon="📝", layout="wide")

st.markdown("# 📝 Data Entry")
st.sidebar.header("Data Entry")

data_type = st.selectbox(
    "Select Data Type to Enter",
    ["Water Usage", "Crop Data", "Soil Data", "Fertilizer Data", "Yield Data"]
)

st.markdown(f"### Enter {data_type}")

if data_type == "Water Usage":
    with st.form("water_usage_form"):
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("Date", date.today())
            field_id = st.text_input("Field ID or Name")
        with col2:
            water_gallons = st.number_input("Water Used (Gallons)", min_value=0.0, format="%.2f")
            source = st.selectbox("Water Source", ["Well", "River", "Canal", "Municipal"])
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Submit Water Usage")
        if submitted:
            st.success(f"Water usage for {field_id} on {entry_date} submitted successfully!")
            # In a real app, you would save this data to a database or file.

elif data_type == "Crop Data":
    with st.form("crop_data_form"):
        col1, col2 = st.columns(2)
        with col1:
            planting_date = st.date_input("Planting Date", date.today())
            field_id = st.text_input("Field ID or Name")
        with col2:
            crop_type = st.selectbox("Crop Type", ["Corn", "Soybeans", "Wheat", "Cotton", "Other"])
            acres_planted = st.number_input("Acres Planted", min_value=0.0, format="%.2f")
        submitted = st.form_submit_button("Submit Crop Data")
        if submitted:
            st.success("Crop data submitted successfully!")

# Add similar st.form sections for Soil, Fertilizer, and Yield data
elif data_type == "Yield Data":
     with st.form("yield_data_form"):
        col1, col2 = st.columns(2)
        with col1:
            harvest_date = st.date_input("Harvest Date", date.today())
            field_id = st.text_input("Field ID or Name")
        with col2:
            total_yield = st.number_input("Total Yield (e.g., bushels, lbs)", min_value=0.0, format="%.2f")
            units = st.text_input("Units (e.g., bushels, lbs)")
        submitted = st.form_submit_button("Submit Yield Data")
        if submitted:
            st.success("Yield data submitted successfully!")
