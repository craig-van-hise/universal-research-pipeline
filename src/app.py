import streamlit as st
import os
import sys
import time
import datetime
import shutil
import pandas as pd
import altair as alt
from pipeline_manager import run_full_pipeline
from drive_manager import DriveManager
from auth_manager import get_login_url, get_token_from_code, get_user_info
import alerts_db
import json

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "../data/user_settings.json")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "../data/search_history.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_settings(settings):
    try:
        # Convert dates to str for JSON
        serializable = {}
        for k, v in settings.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                serializable[k] = v.isoformat()
            else:
                serializable[k] = v
        with open(SETTINGS_FILE, "w") as f:
            json.dump(serializable, f, indent=2)
    except Exception as e:
        print(f"Error saving settings: {e}")

def render_visualizations(csv_path):
    """
    Renders visualizations from the catalog CSV:
    1. Research Timeline (Year Distribution)
    2. Impact Analysis (Citation Counts)
    """
    try:
        df = pd.read_csv(csv_path)
        
        # --- 1. Research Timeline ---
        # Ensure we have a year column
        if 'Year' not in df.columns:
            if 'Publication_Date' in df.columns:
                df['Year'] = df['Publication_Date'].astype(str).str[:4]
        
        if 'Year' in df.columns:
            # Clean Year data
            def clean_year(y):
                try:
                    if pd.isna(y) or str(y).lower() in ['nan', 'none', '']: return "Unknown"
                    return str(int(float(str(y).split('-')[0])))
                except:
                    return "Unknown"
                    
            df['Year_Clean'] = df['Year'].apply(clean_year)
            year_counts = df['Year_Clean'].value_counts().sort_index()
            
            # Rename for tooltip cleanliness
            timeline_data = pd.DataFrame({"Year": year_counts.index, "Count": year_counts.values}).set_index("Year")
            
            st.subheader("Research Timeline")
            st.bar_chart(timeline_data)
            st.divider()

        # --- 2. Impact Analysis (Citation Counts) ---
        print(f"DEBUG: Checking for Citation_Count. Columns: {df.columns}")
        if 'Citation_Count' in df.columns and 'Title' in df.columns:
            # Drop rows with NaN citations, titles
            cit_df = df.dropna(subset=['Citation_Count', 'Title']).copy()
            print(f"DEBUG: Rows after initial drop: {len(cit_df)}")
            
            # Ensure proper types
            cit_df['Citation_Count'] = pd.to_numeric(cit_df['Citation_Count'], errors='coerce').fillna(0)
            cit_df['Authors'] = cit_df['Authors'].fillna("Unknown")
            
            # Sort Layout: Low to High (Ascending)
            cit_df = cit_df.sort_values(by='Citation_Count', ascending=True)
            
            st.subheader("Citation Impact (Low to High)")
            
            c = alt.Chart(cit_df).mark_bar().encode(
                x=alt.X('Title', sort=None, axis=alt.Axis(labels=False, title="Paper Title")),
                y=alt.Y('Citation_Count', title="Citations"),
                tooltip=['Title', 'Authors', 'Citation_Count']
            ).interactive()
            
            st.altair_chart(c, use_container_width=True)
            st.divider()
        
    except Exception as e:
        print(f"Visualization error: {e}")

def save_history(settings):
    try:
        entry = settings.copy()
        entry['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Convert dates
        for k, v in entry.items():
            if isinstance(v, (datetime.date, datetime.datetime)):
                entry[k] = v.isoformat()
        
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        
        history.insert(0, entry) # Newest first
        history = history[:50] # Keep last 50
        
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return pd.DataFrame(json.load(f))
        except: return pd.DataFrame()
    return pd.DataFrame()

@st.dialog("Search History", width="large")
def search_history_modal():
    st.write("Select rows to process.")
    df = load_history()
    
    if df.empty:
        st.info("No history found.")
        if st.button("Close"):
            st.session_state.history_open = False
            st.rerun()
        return

    # Modern Selection API
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        height=400
    )
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("📂 Load Selected", type="primary", use_container_width=True):
            if len(event.selection.rows) == 0:
                st.warning("Select 1 entry.")
            elif len(event.selection.rows) > 1:
                st.error("Select ONLY 1 entry to load.")
            else:
                idx = event.selection.rows[0]
                selected_row = df.iloc[idx].to_dict()
                
                # Restore Dates
                if 'date_start' in selected_row and selected_row['date_start']:
                    try: selected_row['date_start'] = datetime.date.fromisoformat(selected_row['date_start'])
                    except: pass
                if 'date_end' in selected_row and selected_row['date_end']:
                    try: selected_row['date_end'] = datetime.date.fromisoformat(selected_row['date_end'])
                    except: pass
                    
                save_settings(selected_row)
                st.toast("Settings Loaded!", icon="✅")
                time.sleep(0.5)
                # Close modal on load
                st.session_state.history_open = False
                st.rerun()

    with col2:
        if st.button("🗑️ Delete Selected", type="secondary", use_container_width=True):
            if len(event.selection.rows) == 0:
                st.warning("Select entries.")
            else:
                rows_to_delete = event.selection.rows
                try:
                    with open(HISTORY_FILE, "r") as f:
                        full_history = json.load(f)
                    
                    for r_idx in sorted(rows_to_delete, reverse=True):
                        if r_idx < len(full_history):
                            full_history.pop(r_idx)
                            
                    with open(HISTORY_FILE, "w") as f:
                        json.dump(full_history, f, indent=2)
                        
                    st.toast("Entries Deleted.", icon="🗑️")
                    time.sleep(0.5)
                    st.rerun() # This will now re-open the modal because history_open is True
                except Exception as e:
                    st.error(f"Error: {e}")
        
st.set_page_config(
    page_title="ScholarStack",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        min-width: 400px;
        max-width: 800px;
    }
    .stApp > header {
        visibility: hidden;
    }
    [data-testid="stStatusWidget"] {
        visibility: hidden;
    }
    /* Top Right User Profile */
    .user-profile {
        position: fixed;
        top: 60px;
        right: 20px;
        z-index: 999;
        background-color: #f0f2f6;
        padding: 8px 15px;
        border-radius: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .user-avatar {
        width: 30px;
        height: 30px;
        border-radius: 50%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Authentication Logic ---
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

query_params = st.query_params
if "code" in query_params and not st.session_state.credentials:
    code = query_params["code"]
    creds = get_token_from_code(code)
    if creds:
        st.session_state.credentials = creds
        st.session_state.user_info = get_user_info(creds)
        st.query_params.clear()
        st.rerun()

# --- Top Bar ---
if st.session_state.user_info:
    user = st.session_state.user_info
    name = user.get('name', 'User')
    picture = user.get('picture', '')
    st.markdown(f"""
    <div class="user-profile">
        <img src="{picture}" class="user-avatar" onerror="this.style.display='none'">
        <span>{name}</span>
    </div>
    """, unsafe_allow_html=True)
else:
    login_url = get_login_url()
    if login_url:
        st.markdown(f"""
        <a href="{login_url}" target="_self">
            <button style="position: fixed; top: 60px; right: 20px; z-index: 999; background-color: white; border: 1px solid #dadce0; color: #3c4043; padding: 8px 16px; border-radius: 4px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 8px;">
                <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="18">
                Sign in with Google
            </button>
        </a>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <button style="position: fixed; top: 60px; right: 20px; z-index: 999; background-color: #f1f3f4; border: 1px solid #dadce0; color: #9aa0a6; padding: 8px 16px; border-radius: 4px; font-weight: 500; cursor: not-allowed; display: flex; align-items: center; gap: 8px;" title="Upload client_secrets.json to enable">
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="18" style="opacity: 0.5;">
            Sign in with Google (Disabled)
        </button>
        """, unsafe_allow_html=True)

# Initialize Session State
if 'pipeline_run' not in st.session_state:
    st.session_state.pipeline_run = False
if 'zip_path' not in st.session_state:
    st.session_state.zip_path = None
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = None
if 'catalog_content' not in st.session_state:
    st.session_state.catalog_content = None
if 'recent_topics' not in st.session_state:
    st.session_state.recent_topics = []
if 'temp_dir_to_cleanup' not in st.session_state:
    st.session_state.temp_dir_to_cleanup = None
if 'timeline_csv' not in st.session_state:
    st.session_state.timeline_csv = None

st.title("📚 ScholarStack")
st.caption("Your AI Research Librarian")

# --- Success State ---
if st.session_state.pipeline_run and st.session_state.zip_path and os.path.exists(st.session_state.zip_path):
    st.success("✅ Mission Complete! Your library is ready.")
    col_hero_1, col_hero_2, col_hero_3 = st.columns([1, 2, 1])
    with col_hero_2:
        subcol1, subcol2 = st.columns(2)
        with subcol1:
            with open(st.session_state.zip_path, "rb") as f:
                st.download_button("📦 DOWNLOAD ZIP", f, file_name=os.path.basename(st.session_state.zip_path), mime="application/zip", use_container_width=True, type="primary")
        with subcol2:
            if st.button("☁️ Save to Drive", use_container_width=True):
                if not st.session_state.credentials:
                    st.error("Please Sign In (top right) to use Google Drive.")
                elif st.session_state.temp_dir:
                    lib_path = os.path.join(st.session_state.temp_dir, "Library")
                    if os.path.exists(lib_path):
                        with st.spinner("Uploading..."):
                            try:
                                dm = DriveManager(credentials=st.session_state.credentials)
                                count = dm.upload_library(lib_path)
                                st.toast(f"✅ Uploaded {count} papers to Drive.", icon="☁️")
                            except Exception as e:
                                st.error(f"Drive Error: {e}")
                    else:
                        st.error("Library folder not found.")
                else:
                    st.error("Session expired.")
    st.divider()
    if st.session_state.catalog_content:
        st.subheader("📝 Library Catalog Preview")
        with st.container(height=500):
            st.markdown(st.session_state.catalog_content)
        st.divider()
        
    if st.session_state.timeline_csv:
        render_visualizations(st.session_state.timeline_csv)

# --- Sidebar ---
with st.sidebar:
    if st.button("📜 View Search History", use_container_width=True):
        st.session_state.history_open = True
        st.rerun()
        
    if st.session_state.get('history_open', False):
        search_history_modal()
    st.divider()
    
    # --- Alert Management ---
    with st.expander("📬 Manage Alerts"):
        st.write("**Save Current Search as Alert**")
        
        # Initialize alerts database
        alerts_db.init_db()
        
        alert_email = st.text_input(
            "Email for notifications",
            placeholder="your.email@gmail.com",
            key="alert_email_input"
        )
        
        if st.button("💾 Save Current Search as Alert", use_container_width=True):
            if not alert_email or '@' not in alert_email:
                st.error("Please enter a valid email address")
            else:
                # Get current search parameters
                current_topic = st.session_state.get('topic_input', '')
                current_keywords = st.session_state.get('keywords_input_std', '')
                
                if not current_topic and not current_keywords:
                    st.warning("Please enter a topic or keywords first")
                else:
                    query = f"{current_topic} + {current_keywords}" if current_keywords else current_topic
                    sub_id = alerts_db.add_subscription(
                        email=alert_email,
                        query=query,
                        source="OpenAlex"
                    )
                    st.success(f"✅ Alert saved! (ID: {sub_id})")
                    st.rerun()
        
        st.divider()
        st.write("**Active Alerts**")
        
        subscriptions = alerts_db.get_all_subscriptions()
        
        if not subscriptions:
            st.info("No alerts saved yet")
        else:
            for sub in subscriptions:
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    status_icon = "✅" if sub['active'] else "⏸️"
                    st.write(f"{status_icon} **{sub['search_query']}**")
                    st.caption(f"To: {sub['user_email']}")
                
                with col2:
                    new_state = not sub['active']
                    btn_label = "Pause" if sub['active'] else "Resume"
                    if st.button(btn_label, key=f"toggle_{sub['id']}", use_container_width=True):
                        alerts_db.toggle_subscription(sub['id'], new_state)
                        st.rerun()
                
                with col3:
                    if st.button("🗑️", key=f"delete_{sub['id']}", use_container_width=True):
                        alerts_db.delete_subscription(sub['id'])
                        st.rerun()
    
    st.divider()

    st.header("Research Parameters")
    
    if st.session_state.recent_topics:
        st.write("Recent Topics:")
        cols = st.columns(len(st.session_state.recent_topics))
        for i, t in enumerate(st.session_state.recent_topics):
            if st.button(t, key=f"topic_btn_{i}"):
                st.session_state.selected_topic = t
        if st.button("Clear History", type="secondary"):
            st.session_state.recent_topics = []
            st.rerun()

    # --- Load Settings ---
    saved = load_settings()    
    
    # Defaults logic
    def get_setting(key, default):
        # Prefer session state if set (from buttons), else saved, else default
        return saved.get(key, default)

    default_topic = st.session_state.get('selected_topic', get_setting('topic', ""))
    default_keywords = get_setting('keywords', "")
    
    # Logic Map for Radio Index
    logic_saved = get_setting('keyword_logic', 'Match Any (OR)')
    logic_idx = 0 if "Any" in logic_saved else 1
    
    default_author = get_setting('author', "")
    default_pub = get_setting('publication', "")
    default_count = get_setting('count', 10)
    
    sort_saved = get_setting('sort_method', "Most Relevant")
    sort_opts = ["Most Relevant", "Date: Newest", "Date: Oldest", "Citations: Most", "Citations: Least"]
    try: sort_idx = sort_opts.index(sort_saved)
    except: sort_idx = 0
    
    auto_saved = get_setting('auto_folders', True)
    key_sub_saved = get_setting('use_keywords_subfolders', False)
    
    # Dates
    use_start_saved = get_setting('use_start_date', False)
    use_end_saved = get_setting('use_end_date', False)
    try: d_start_saved = datetime.date.fromisoformat(get_setting('date_start', "2023-01-01"))
    except: d_start_saved = datetime.date.today() - datetime.timedelta(days=365*2)
    try: d_end_saved = datetime.date.fromisoformat(get_setting('date_end', "2025-01-01"))
    except: d_end_saved = datetime.date.today()
    
    # REVERTED: Back to standard text_input
    topic = st.text_input(
        "Research Topic (Required)", 
        value=default_topic, 
        placeholder="e.g., Generative Audio",
        key="topic_input_std"
    )
    
    keywords = st.text_input(
        "Additional Keywords (Comma-separated)", 
        value=default_keywords,
        placeholder="e.g., crosstalk cancellation, binaural synthesis",
        key="keywords_input_std"
    )


    keyword_logic = st.radio(
        "Keyword Logic",
        options=["Match Any (OR)", "Match All (AND)"],
        index=logic_idx,
        horizontal=True,
        help="Choose 'Match Any' to find papers containing ANY of the comma-separated keywords. Choose 'Match All' to find papers containing ALL of them."
    )
    
    logic_val = "any" if "Any" in keyword_logic else "all"
    
    with st.expander("Advanced Filters"):
        author = st.text_input("Author", value=default_author, placeholder="e.g., Yann LeCun", key="author_input")
        publication = st.text_input("Publication/Venue", value=default_pub, placeholder="e.g., ICASSP", key="pub_input")
        
        st.write("Date Range:")
        col_d1, col_d2 = st.columns(2)
        use_start_date = st.checkbox("Start Date", value=use_start_saved)
        use_end_date = st.checkbox("End Date", value=use_end_saved)
        today = datetime.date.today()
        
        d_start_val = st.date_input("From", value=d_start_saved, max_value=today) if use_start_date else None
        d_end_val = st.date_input("To", value=d_end_saved, max_value=today) if use_end_date else None
        
        all_sites = st.checkbox("Select All Sources", value=True)
        site_options = ["ArXiv", "Scholar", "Semantic Scholar", "CORE", "DOAJ"]
        site_map = {"ArXiv": "arxiv", "Scholar": "scholar", "Semantic Scholar": "semantic", "CORE": "core", "DOAJ": "doaj"}
        selected_sites_labels = site_options if all_sites else [s for s in site_options if st.checkbox(s, value=True)]
        selected_sites = [site_map[label] for label in selected_sites_labels]

    count = st.number_input("Target Paper Count", min_value=1, max_value=1000, value=default_count)
    
    sort_method = st.radio(
        "Prioritize By",
        options=sort_opts,
        index=sort_idx,
        help="Decides which papers to keep when trimming the list to your Target Count."
    )
    
    st.write("Organization:")
    col_org1, col_org2 = st.columns(2)
    auto_folders = col_org1.checkbox("Enable AI Auto-Categorization", value=auto_saved, help="Use LLM to sort papers into sub-folders.")
    use_keywords_subfolders = col_org2.checkbox("Use Keywords as Sub-folders", value=key_sub_saved, help="Create a parent folder for each Search Term/Keyword.")
    
    filename_format_saved = get_setting('filename_format', "Title")
    filename_format = st.selectbox(
        "PDF Filename Format",
        options=["Title", "Author - Year - Title", "Year - Journal - Title"],
        index=["Title", "Author - Year - Title", "Year - Journal - Title"].index(filename_format_saved) if filename_format_saved in ["Title", "Author - Year - Title", "Year - Journal - Title"] else 0,
        help="Choose how downloaded PDF files should be named."
    )
    
    st.divider()
    
    # Removed Settings Section as requested
    user_api_key = os.getenv("GOOGLE_API_KEY")
    
    start_btn = st.button("🚀 Start Research Mission", type="primary")

# --- Execution ---
if start_btn:
    if not topic:
        st.error("Please enter a Research Topic.")
    else:
        st.session_state.pipeline_run = False
        st.session_state.zip_path = None
        st.session_state.catalog_content = None
        st.session_state.timeline_csv = None # Reset timeline
        st.session_state.history_open = False # Prevent zombie modal
        
        if st.session_state.temp_dir_to_cleanup:
            try: shutil.rmtree(st.session_state.temp_dir_to_cleanup)
            except: pass

        if topic not in st.session_state.recent_topics:
            st.session_state.recent_topics.insert(0, topic)
            if len(st.session_state.recent_topics) > 5: st.session_state.recent_topics.pop()
        
        # --- Persistence & History ---
        current_settings = {
            "topic": topic,
            "keywords": keywords,
            "keyword_logic": keyword_logic,
            "author": author,
            "publication": publication,
            "count": count,
            "sort_method": sort_method,
            "auto_folders": auto_folders,
            "use_keywords_subfolders": use_keywords_subfolders,
            "filename_format": filename_format,
            "use_start_date": use_start_date,
            "use_end_date": use_end_date,
            "date_start": d_start_val,
            "date_end": d_end_val
        }
        save_settings(current_settings)
        save_history(current_settings)
        # -----------------------------
        
        st.subheader("📡 Mission Control Log")
        log_container = st.empty()
        full_log = ""
        status_box = st.status("Initializing Agent...", expanded=True)
        
        try:
            status_box.write("🔍 Phase 1: Scouting Academic Sources...")
            d_start_str = d_start_val.strftime("%Y-%m-%d") if d_start_val else None
            d_end_str = d_end_val.strftime("%Y-%m-%d") if d_end_val else None

            api_key_to_use = user_api_key if user_api_key else None

            pipeline_gen = run_full_pipeline(
                topic=topic,
                keywords=keywords,
                keyword_logic=logic_val,
                author=author,
                publication=publication,
                date_start=d_start_str,
                date_end=d_end_str,
                sites=selected_sites,
                count=count,
                sort_method=sort_method,
                google_api_key=api_key_to_use,
                auto_folders=auto_folders,
                use_keywords=use_keywords_subfolders,
                filename_format=filename_format
            )
            
            final_zip_path = None
            temp_dir = None
            
            for line in pipeline_gen:
                if isinstance(line, tuple):
                    if line[0] == "RETURN_PATH": final_zip_path = line[1]
                    elif line[0] == "TEMP_DIR": temp_dir = line[1]
                    elif line[0] == "CATALOG_CSV":
                        # Render visualizations immediately AND save for persistence
                        render_visualizations(line[1])
                        st.session_state.timeline_csv = line[1]
                else:
                    full_log += line + "\n"
                    log_container.code(full_log, language="bash")

            if final_zip_path and os.path.exists(final_zip_path):
                status_box.update(label="Mission Complete!", state="complete", expanded=False)
                st.session_state.pipeline_run = True
                st.session_state.zip_path = final_zip_path
                st.session_state.temp_dir = temp_dir
                st.session_state.temp_dir_to_cleanup = temp_dir
                
                found_catalog = False
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(".md") and "Catalog" in file:
                            with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                                st.session_state.catalog_content = f.read()
                            found_catalog = True; break
                    if found_catalog: break
                
                st.rerun()
            else:
                status_box.update(label="Mission Failed", state="error")
                st.error("Pipeline finished, but no output was generated.")
        except Exception as e:
            status_box.update(label="System Error", state="error")
            st.error(f"An error occurred: {e}")

if not start_btn and not st.session_state.pipeline_run:
    st.info("👈 Use the sidebar to configure your research mission.")

st.divider()
st.caption("Universal Research Pipeline | Built with Streamlit, Python, and Google Gemini.")
