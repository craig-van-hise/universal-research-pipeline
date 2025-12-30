

### **Refactor Task: Metadata Standardization & Multi-Format Export**

**Context:**
The "Librarian" app currently downloads papers and generates a `catalog.md` file. We are upgrading the metadata engine.
**Constraint:** Do NOT change the downloading or folder organization logic. Only refactor the **metadata dictionary** and the **export file generation**.

**The Goal:**
We need to standardize our internal metadata format and then output that data into **three** specific files for the user:

1. `catalog.md` (Existing feature - must be preserved and updated)
2. `catalog.csv` (New feature - for data analysis)
3. `citations.ris` (New feature - for Zotero/EndNote)

---

### **Step 1: Standardize the Internal Metadata Dictionary**

Ensure your paper objects/dictionaries now strictly use these keys. If data is missing from the API, default to `None` or `""`.

* **Keys:** `title`, `authors` (list of strings), `year` (YYYY), `date` (YYYY-MM-DD), `journal` (or venue), `doi`, `url` (source link), `pdf_url` (direct link), `abstract`, `citation_count`, `filename` (local filename).

---

### **Step 2: Update the Existing Markdown Generator (`catalog.md`)**

You are already generating this file. Update the function to add the new standard keys above. Keep existing keys not covered by the new ones (such as "status"). Make sure the .md version retiains the "Search Settings" section.

* **Format:** Keep the existing table format for readability.
* **Columns:** `| Title | First Author | Year | Journal | Citations | Link |`
* **Rule:** For the "Link" column, use the `url` field formatted as a Markdown link `[Source](url)`.
* **Rule:** For "First Author", only take the first item from the `authors` list and append "et al." if the list length is > 1.
* **Note:** Do not put the `abstract` in the table.

---

### **Step 3: Implement New Export Formats**

#### **A. Generate `catalog.csv**`

Create a function to dump the full metadata into a CSV.

* **Columns:** `Title`, `Authors` (join list with semicolon), `Year`, `Journal`, `DOI`, `Citation_Count`, `URL`, `PDF_Link`, `Filename`, `Abstract`.
* **Critical:** Use a CSV library to strictly handle escaping. The `Abstract` and `Title` fields often contain commas and newlines that will break the file if not quoted correctly.

#### **B. Generate `citations.ris**`

Create a function to generate an RIS file for reference managers.

* **Strict Formatting:**
* Start record: `TY  - JOUR` (Two spaces after TY, one after hyphen)
* End record: `ER  - `


* **Tag Mapping:**
* `TI`: `title`
* `AU`: `authors` (Loop through list: create a separate `AU  - Name` line for **every** author).
* `PY`: `year`
* `JO`: `journal`
* `DO`: `doi`
* `UR`: `url`
* `L1`: `pdf_url` (**Important:** This maps the direct PDF link).
* `AB`: `abstract`



**Output:**
Return the code that takes the list of paper objects and generates the strings for `catalog.md`, `catalog.csv`, and `citations.ris`.