import streamlit as st
import pandas as pd
import requests

# --- Simple Debugging Script ---
st.title("API Column Name Finder")

# Get your API key from secrets
API_KEY = st.secrets.get("OPENET_API_KEY")
if not API_KEY:
    st.error("API Key not found in secrets!")
else:
    if st.button("Run API Test"):
        with st.spinner("Calling the OpenET API..."):
            API_URL = "https://openet-api.org/raster/timeseries/point"
            
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": API_KEY
            }
            
            # A hardcoded payload for a quick test
            payload = {
                "date_range": ["2024-01-01", "2024-03-31"],
                "file_format": "JSON",
                "geometry": [-100.0, 39.0], # A point in Kansas
                "interval": "monthly",
                "model": "Ensemble",
                "reference_et": "gridMET",
                "units": "mm",
                "variable": "ET"
            }

            try:
                response = requests.post(API_URL, headers=headers, json=payload)
                response.raise_for_status()
                
                data = response.json()
                df = pd.DataFrame(data)

                st.success("API Call Successful! Here is the data:")
                
                # THIS IS THE MOST IMPORTANT PART
                st.write("👇 The actual column names are:")
                st.code(df.columns.tolist(), language="python")

                st.write("👇 And here is a preview of the data table:")
                st.dataframe(df)

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.json(response.json())
