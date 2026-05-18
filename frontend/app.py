# frontend/app.py
import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"  # replace with EC2 backend IP when deployed

st.title("🧠 AI Complaint Categorization System")

# --- Authentication ---
st.sidebar.header("Account")

if "token" not in st.session_state:
    st.session_state["token"] = None

username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")

col1, col2 = st.sidebar.columns(2)
if col1.button("Login"):
    resp = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
    if resp.status_code == 200:
        try:
            st.session_state["token"] = resp.json()["access_token"]
            st.sidebar.success("Logged in successfully!")
        except Exception:
            st.sidebar.error("Login succeeded but response was not JSON")
    else:
        try:
            st.sidebar.error(resp.json().get("detail", "Incorrect Username/Password"))
        except Exception:
            st.sidebar.error(resp.text or "Incorrect Username/Password")

if col2.button("Register"):
    resp = requests.post(f"{API_URL}/register", data={"username": username, "password": password})
    if resp.status_code == 200:
        st.sidebar.success("Account created successfully! Please login.")
    else:
        try:
            st.sidebar.error(resp.json().get("detail", "Registration failed"))
        except Exception:
            st.sidebar.error(resp.text or "Registration failed")

headers = {"Authorization": f"Bearer {st.session_state['token']}"} if st.session_state["token"] else {}

# --- Require login ---
if not st.session_state["token"]:
    st.warning("⚠️ Please login to access the system.")
else:
    # --- Tabs ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Classify Complaint", "View Complaints", "Search", "Analytics", "Upload File"
    ])

    # --- Tab 1: Classify Complaint ---
    with tab1:
        if "complaint_input" not in st.session_state:
            st.session_state.complaint_input = ""

        user_input = st.text_area("Enter your complaint:", key="complaint_input")
        if st.button("Classify Complaint"):
            if user_input.strip():
                response = requests.post(f"{API_URL}/predict", json={"complaint": user_input}, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    st.success(f"Predicted Category: {result['category']}")
                    # st.session_state.complaint_input = ""
                else:
                    st.error("Error connecting to API")
            else:
                st.error("Enter a complaint first!")
        # if st.button("Clear"):
        #     st.session_state.complaint_input=""

    # --- Tab 2: View Complaints ---
    with tab2:
        st.subheader("📂 Stored Complaints")
        response = requests.get(f"{API_URL}/complaints", headers=headers)
        if response.status_code == 200:
            df = pd.DataFrame(response.json())
            if df.empty:
                st.info("No complaints stored yet.")
            else:
                df = df.drop(columns=["id"], errors="ignore")
                df.reset_index(drop=True, inplace=True)

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

                st.subheader("🔄 Update Complaint Status")
                if not filtered_df.empty:
                    selected_id = st.selectbox("Select Complaint ID to update:", filtered_df['ComplaintID'])
                    new_status = st.selectbox("New Status:", ["In Progress", "Resolved"])
                    if st.button("Update Status"):
                        numeric_id = int(selected_id.replace("#C", ""))
                        resp = requests.put(f"{API_URL}/update_status",
                                            params={"complaint_id": numeric_id, "new_status": new_status},
                                            headers=headers)
                        if resp.status_code == 200:
                            st.success(resp.json()["message"])
                        else:
                            st.error("Error updating status")
        else:
            st.error("Error fetching complaints from API")

    # --- Tab 3: Search Complaints ---
    with tab3:
        st.subheader("🔍 Search Complaints")
        keyword = st.text_input("Keyword")
        category = st.text_input("Category")
        start_date = st.date_input("Start Date", value=None)
        end_date = st.date_input("End Date", value=None)

        if st.button("Search"):
            params = {}
            if keyword: params["keyword"] = keyword
            if category: params["category"] = category
            if start_date: params["start_date"] = str(start_date)
            if end_date: params["end_date"] = str(end_date)
            resp = requests.get(f"{API_URL}/search", params=params, headers=headers) #type:ignore
            if resp.status_code == 200:
                st.dataframe(pd.DataFrame(resp.json()))
            else:
                st.error("Search failed")

    # --- Tab 4: Analytics ---
    with tab4:
        st.subheader("📊 Analytics")
        resp = requests.get(f"{API_URL}/stats", headers=headers)
        if resp.status_code == 200:
            stats = resp.json()
            st.metric("Total Complaints", stats["total_complaints"])
            st.metric("Resolution Rate (%)", round(stats["resolution_rate"], 2))
            st.bar_chart(pd.DataFrame.from_dict(stats["by_category"], orient="index", columns=["Count"]))
        else:
            st.error("Error fetching stats")

    # --- Tab 5: Upload File ---
    with tab5:
        st.subheader("📂 Upload Complaint File")
        uploaded_file = st.file_uploader("Upload a text file", type=["txt"])
        if uploaded_file and st.button("Classify File"):
            files = {"file": uploaded_file.getvalue()}
            resp = requests.post(f"{API_URL}/upload", files=files, headers=headers)
            if resp.status_code == 200:
                result = resp.json()
                st.success(f"Predicted Category: {resp.json()['category']}")
            else:
                st.error("File classification failed")
