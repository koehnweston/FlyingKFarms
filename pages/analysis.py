import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Data Analysis", page_icon="🔬", layout="wide")

st.markdown("# 🔬 Data Analysis")
st.sidebar.header("Data Analysis")
st.write(
    """This page is a placeholder for your data analysis. You can build charts
       and tables to analyze relationships between different data sources."""
)

# Placeholder: Load some sample data
@st.cache_data
def load_data():
    data = pd.DataFrame(
        np.random.rand(100, 5),
        columns=['Water Usage', 'Fertilizer Applied', 'Soil Moisture', 'Temperature', 'Yield']
    )
    data['Yield'] = data['Yield'] * 200 # Scale yield
    return data

df = load_data()

st.subheader("Explore Data Relationships")

x_axis = st.selectbox("Select X-axis", df.columns)
y_axis = st.selectbox("Select Y-axis", df.columns, index=4)

st.write(f"### {y_axis} vs. {x_axis}")
st.scatter_chart(df, x=x_axis, y=y_axis)

st.subheader("Raw Data Table")
st.dataframe(df)
