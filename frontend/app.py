import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"  # replace with EC2 public IP when deployed

st.title("🧠 AI Complaint Categorization System")
tab1, tab2 = st.tabs(["Classify Complaint", "View Complaints"])

# --- Tab 1: Classify Complaint ---
with tab1:
    st.write("Enter a financial complaint and the system will categorize it automatically.")
    user_input = st.text_area("Enter your complaint:")

    if st.button("Classify Complaint"):
        if user_input.strip():
            response = requests.post(f"{API_URL}/predict", json={"complaint": user_input})
            if response.status_code == 200:
                result = response.json()
                st.success(f"Predicted Category: {result['category']} (submitted on {result['submitted_on']})")
            else:
                st.error("Error connecting to API")
        else:
            st.error("Enter a financial complaint first !!")

# --- Tab 2: View Complaints ---
with tab2:
    st.subheader("📂 Stored Complaints")
    response = requests.get(f"{API_URL}/complaints")
    if response.status_code == 200:
        df = pd.DataFrame(response.json())
        if df.empty:
            st.info("No complaints stored yet.")
        else:
            categories = df['category'].unique().tolist()
            selected_cat = st.selectbox("Filter by category:", ["All"] + categories)

            statuses = df['status'].unique().tolist()
            selected_status = st.selectbox("Filter by status:", ["All"] + statuses)

            filtered_df = df.copy()
            if selected_cat != "All":
                filtered_df = filtered_df[filtered_df['category'] == selected_cat]
            if selected_status != "All":
                filtered_df = filtered_df[filtered_df['status'] == selected_status]

            st.dataframe(filtered_df)
    else:
        st.error("Error fetching complaints from API")
