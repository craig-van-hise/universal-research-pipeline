
# Product Requirements Prompt: UI Overhaul for ScholarStack

**Role:** Expert Python Streamlit Developer & UI/UX Designer
**Goal:** Refactor the existing `src/app.py` and configuration files to transition the app from a "default data tool" look to a "modern student SaaS" aesthetic.
**Tone:** Clean, Minimalist, Gen-Z Friendly (Notion-style).

## 1. Dependency Updates

* **Action:** Check `requirements.txt`.
* **Requirement:** Ensure `streamlit-extras` is installed. If not, add it.
* *Reasoning:* We need this for the `stylable_container` and `metric_cards`.



## 2. Global Theming (`.streamlit/config.toml`)

* **Action:** Create or Overwrite `.streamlit/config.toml` with the following palette to remove the "Danger Red" and establish a modern identity.
* **Code Block:**
```toml
[theme]
primaryColor = "#6C63FF"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F7F7F9"
textColor = "#262730"
font = "sans serif"
[server]
runOnSave = true

```



## 3. UI Refactoring (`src/app.py`)

### A. The "Fake" Navigation Bar

* **Context:** The Google Sign-in button currently floats awkwardly. We need a top-aligned header.
* **Implementation:**
1. At the very top of the app (inside `main()`), create a 2-column layout: `col_brand, col_auth = st.columns([3, 1], gap="medium")`.
2. **Left Column (`col_brand`):** Render the Logo and Title ("ScholarStack") using Markdown. Add the subtitle "Your AI Research Librarian" as a caption.
3. **Right Column (`col_auth`):**
* Align content to the right.
* **Logic:** If the user is **NOT** logged in, display the "Sign in with Google" button.
* **Logic:** If the user **IS** logged in, display a circular avatar or user initial using `st.popover` (e.g., "👤 J"). Inside the popover, put "Settings" and "Log Out".


4. **Divider:** Add `st.divider()` immediately after this section to separate the header from the app body.



### B. The "Hero" Action Area

* **Context:** The red "Start Mission" button and blue info box are too aggressive/corporate.
* **Implementation:**
1. **Remove** the `st.info("Use the sidebar...")` banner. Replace it with `st.toast("👋 Welcome to ScholarStack! Check the sidebar to start.")` that triggers on load.
2. **Center the Action:** Create a centered column layout for the main start button so it doesn't stretch full width.
3. **Button Styling:** Use a primary button for "🚀 Start Mission".
4. **Feedback Loop:** When "Start Mission" is clicked, replace the old progress bars with `st.status`.
* *Example Pattern:*
```python
with st.status("🤖 Librarian is working...", expanded=True) as status:
    st.write("Searching OpenAlex...")
    # [Existing Logic Here]
    status.update(label="Mission Complete!", state="complete", expanded=False)

```







### C. CSS Injection (Clean Up)

* **Action:** Inject the following CSS at the start of the app to hide default Streamlit clutter and round the buttons.
* **Code Block:**
```python
st.markdown("""
    <style>
        /* Hide Streamlit 'Deploy' button and hamburger menu */
        .stDeployButton {visibility: hidden;}

        /* Remove top padding so the logo sits high like a nav bar */
        .block-container { padding-top: 2rem; }

        /* Round the buttons for a modern app feel */
        div.stButton > button {
            border-radius: 12px;
            box-shadow: 0px 2px 4px rgba(0,0,0,0.1);
            transition: all 0.2s ease;
        }
        div.stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0px 4px 8px rgba(0,0,0,0.2);
        }
    </style>
""", unsafe_allow_html=True)

```



## 4. Execution Plan

1. Apply `config.toml` changes first to set the color baseline.
2. Refactor `app.py` header layout to fix the Google Button positioning.
3. Inject the CSS to clean the UI.
4. Update the "Start Mission" flow to use `st.status` and `st.toast`.