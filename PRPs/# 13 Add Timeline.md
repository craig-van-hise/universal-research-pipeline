
### **PRP Publication Timeline Visualization**


**Context:**
We want to give users immediate visual feedback on the search results in the Streamlit app *before* they download. We will add a "Publication Timeline" histogram.

**The Task:**

1. **Data Extraction:** Create a helper function that iterates through the list of found papers and extracts the `year` field. Handle `None` or missing years by categorizing them as "Unknown".
2. **Visualization:** Use Streamlit's native `st.bar_chart` or `st.altair_chart` to render a histogram.
* **X-Axis:** Year (sorted chronologically).
* **Y-Axis:** Count of papers.
* **Tooltip:** If using Altair, show the exact count on hover.


3. **UI Placement:** Insert this chart in the main `app.py` workflow immediately after the search completes but *before* the "Download ZIP" button appears.
* Add a subheader: `## Research Timeline`.



**Output:**
Return the Python code to generate the year-distribution dictionary and the Streamlit code to render the chart.

---
