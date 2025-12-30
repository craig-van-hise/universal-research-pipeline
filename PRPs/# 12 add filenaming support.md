

### **PRP: Filename Customization (The Renamer)**

**Context:**
Users currently receive PDFs with default filenames that are often hard to read. We need to allow users to customize the naming convention of downloaded PDFs via the Streamlit interface.

**The Task:**

1. **Update UI:** Add a selectbox in the Streamlit Sidebar under "Settings" labeled "PDF Filename Format".
* **Options:**
* `Title` (Default)
* `Author - Year - Title`
* `Year - Journal - Title`




2. **Update Logic:** Refactor the `save_pdf()` or `download_paper()` function to respect this setting.
3. **Sanitization (Critical):**
* You must implement a strict string sanitizer. Paper titles often contain illegal characters for file systems (`:`, `/`, `\`, `?`, `*`, `"`, `<`, `>`, `|`).
* Replace these characters with an underscore `_` or a dash `-`.
* Truncate filenames to 255 characters max to prevent OS errors.


4. **Metadata Sync:** Ensure that whatever filename is chosen is updated in the `index.json` and the `Catalog_Summary.md` so the links still work.

**Output:**
Return the updated Streamlit UI code snippet and the refactored PDF saving logic containing the sanitization function.
