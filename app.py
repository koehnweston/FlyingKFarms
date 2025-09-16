session_key = f'data_{selected_section}'
    if st.session_state.get(session_key) is not None:
        st.markdown("---")
        st.subheader(f"OpenET Data for Section: {selected_section}")
        df_to_show = st.session_state[session_key]

        if 'ET (in)' in df_to_show.columns:
            st.markdown("##### Daily Evapotranspiration (ET)")
            st.line_chart(df_to_show['ET (in)'])
        
        if 'Precipitation (in)' in df_to_show.columns:
            st.markdown("##### Daily Precipitation")
            st.bar_chart(df_to_show['Precipitation (in)'])

        if 'NDVI' in df_to_show.columns:
            st.markdown("##### Daily NDVI")
            st.line_chart(df_to_show['NDVI'])
        
        if 'ET (in)' in df_to_show.columns:
            df_to_show['Cumulative ET (in)'] = df_to_show['ET (in)'].cumsum()
            st.markdown("##### Cumulative Water Use (ET)")
            st.line_chart(df_to_show['Cumulative ET (in)'])

        if 'Precipitation (in)' in df_to_show.columns:
            df_to_show['Cumulative Precipitation (in)'] = df_to_show['Precipitation (in)'].cumsum()
            st.markdown("##### Cumulative Precipitation")
            st.line_chart(df_to_show['Cumulative Precipitation (in)'])

        # --- UPDATED PLOT WITH MONOTONIC CALCULATION ---
        if 'ET (in)' in df_to_show.columns and 'Precipitation (in)' in df_to_show.columns:
            # Fill any missing values with 0 for the calculation
            et_daily = df_to_show['ET (in)'].fillna(0)
            precip_daily = df_to_show['Precipitation (in)'].fillna(0)
            
            # Calculate the daily deficit, but set it to 0 if negative (i.e., on rainy days)
            # This ensures we only accumulate on days where ET > Precip
            daily_groundwater_use = (et_daily - precip_daily).clip(lower=0)
            
            # Create the monotonically increasing cumulative sum
            df_to_show['Consumed Groundwater (in)'] = daily_groundwater_use.cumsum()
            
            # Update the markdown title
            st.markdown("##### Consumed Groundwater (in)")
            
            # Plot the newly named column
            st.line_chart(df_to_show['Consumed Groundwater (in)'])


        st.markdown("---")
        st.markdown("##### Raw Data")
        st.dataframe(df_to_show)
