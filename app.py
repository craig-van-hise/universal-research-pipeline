import streamlit as st
import os
import sys
import datetime
import shutil
from pipeline_manager import run_full_pipeline
from drive_manager import DriveManager
from auth_manager import get_login_url, get_token_from_code, get_user_info

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

# --- Sidebar ---
with st.sidebar:
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

    default_topic = st.session_state.get('selected_topic', "")
    
    # REVERTED: Back to standard text_input
    topic = st.text_input(
        "Research Topic (Required)", 
        value=default_topic, 
        placeholder="e.g., Generative Audio",
        key="topic_input_std"
    )
    
    # REVERTED: Back to standard text_input
    keywords = st.text_input(
        "Additional Keywords (Comma-separated)", 
        placeholder="e.g., crosstalk cancellation, binaural synthesis",
        key="keywords_input_std"
    )

    keyword_logic = st.radio(
        "Keyword Logic",
        options=["Match Any (OR)", "Match All (AND)"],
        index=0,
        horizontal=True,
        help="Choose 'Match Any' to find papers containing ANY of the comma-separated keywords. Choose 'Match All' to find papers containing ALL of them."
    )
    
    logic_val = "any" if "Any" in keyword_logic else "all"
    
    with st.expander("Advanced Filters"):
        author = st.text_input("Author", placeholder="e.g., Yann LeCun", key="author_input")
        publication = st.text_input("Publication/Venue", placeholder="e.g., ICASSP", key="pub_input")
        
        st.write("Date Range:")
        col_d1, col_d2 = st.columns(2)
        use_start_date = st.checkbox("Start Date", value=True)
        use_end_date = st.checkbox("End Date", value=True)
        today = datetime.date.today()
        default_start = today - datetime.timedelta(days=365*2)
        
        d_start_val = st.date_input("From", value=default_start, max_value=today) if use_start_date else None
        d_end_val = st.date_input("To", value=today, max_value=today) if use_end_date else None
        
        all_sites = st.checkbox("Select All Sources", value=True)
        site_options = ["ArXiv", "Scholar", "Semantic Scholar", "CORE", "DOAJ"]
        site_map = {"ArXiv": "arxiv", "Scholar": "scholar", "Semantic Scholar": "semantic", "CORE": "core", "DOAJ": "doaj"}
        selected_sites_labels = site_options if all_sites else [s for s in site_options if st.checkbox(s, value=True)]
        selected_sites = [site_map[label] for label in selected_sites_labels]

    count = st.number_input("Target Paper Count", min_value=1, max_value=200, value=10)
    
    st.divider()
    
    st.header("Settings")
    # google_api_key = st.text_input("Gemini API Key (Optional)", type="password", help="Required only for clustering stage")
    # if google_api_key:
    #     os.environ["GOOGLE_API_KEY"] = google_api_key
    user_api_key = os.getenv("GOOGLE_API_KEY")
    
    st.divider()
    
    start_btn = st.button("🚀 Start Research Mission", type="primary")

# --- Execution ---
if start_btn:
    if not topic:
        st.error("Please enter a Research Topic.")
    else:
        st.session_state.pipeline_run = False
        st.session_state.zip_path = None
        st.session_state.catalog_content = None
        
        if st.session_state.temp_dir_to_cleanup:
            try: shutil.rmtree(st.session_state.temp_dir_to_cleanup)
            except: pass

        if topic not in st.session_state.recent_topics:
            st.session_state.recent_topics.insert(0, topic)
            if len(st.session_state.recent_topics) > 5: st.session_state.recent_topics.pop()
        
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
                google_api_key=api_key_to_use
            )
            
            final_zip_path = None
            temp_dir = None
            
            for line in pipeline_gen:
                if isinstance(line, tuple):
                    if line[0] == "RETURN_PATH": final_zip_path = line[1]
                    elif line[0] == "TEMP_DIR": temp_dir = line[1]
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
