
You are acting as a Senior Python Developer optimizing the **ScholarStack** project. We are currently facing a critical bottleneck in our search pipeline: the `Crossref -> Unpaywall` check loop is too slow and has a low yield of valid PDFs.

Your task is to integrate the **OpenAlex API** as the primary search source to resolve this. OpenAlex allows server-side filtering for Open Access (`is_oa:true`), which will eliminate the need for thousands of individual HTTP checks.

Please modify `1_search_omni.py` (and create a new utility file if necessary) to implement the following changes:

### 1. Implement the Abstract Reconstructor

OpenAlex stores abstracts as an "Inverted Index" to save space. We need this helper function to reconstruct them into readable text so our Gemini agent can categorize the papers later.

```python
def reconstruct_abstract(inverted_index):
    """
    Reconstructs the abstract from OpenAlex's inverted index format.
    """
    if not inverted_index:
        return ""
    
    # Determine the length of the abstract based on the max index
    max_index = 0
    for positions in inverted_index.values():
        if positions:
            max_index = max(max_index, max(positions))
    
    words = [""] * (max_index + 1)
    
    # Populate the words at their correct positions
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
            
    return " ".join(words)

```

### 2. Implement the OpenAlex Search Function

Create a function `search_openalex` that handles pagination and standardizes the output to match our existing dictionary format.

**Requirements:**

* **Filter:** Must use `filter="is_oa:true,has_doi:true"` to ensure we only get valid, free papers.
* **Fields:** Request specific fields to save bandwidth: `title,id,publication_year,open_access,authorships,abstract_inverted_index`.
* **Logic:** Loop through pages until `target_count` is met.

```python
import requests

def search_openalex(query, target_count=50, start_year=None, end_year=None):
    base_url = "https://api.openalex.org/works"
    papers = []
    per_page = 200
    
    # Build filter string
    filters = ["is_oa:true", "has_doi:true"]
    if start_year:
        filters.append(f"publication_year:>{start_year-1}")
    if end_year:
        filters.append(f"publication_year:<{end_year+1}")
    
    filter_str = ",".join(filters)
    current_page = 1
    
    print(f"📚 Querying OpenAlex for: '{query}'...")

    while len(papers) < target_count:
        params = {
            "search": query,
            "filter": filter_str,
            "per-page": per_page,
            "page": current_page,
            "select": "title,id,publication_year,open_access,authorships,abstract_inverted_index"
        }

        try:
            resp = requests.get(base_url, params=params, timeout=10)
            if resp.status_code != 200: 
                break
                
            results = resp.json().get('results', [])
            if not results: 
                break
                
            for item in results:
                pdf_url = item.get('open_access', {}).get('oa_url')
                if not pdf_url: continue

                # Reconstruct abstract
                abstract_text = reconstruct_abstract(item.get('abstract_inverted_index'))

                # Get author
                authors = item.get('authorships', [])
                first_author = authors[0]['author']['display_name'] if authors else "Unknown"

                papers.append({
                    "title": item['title'],
                    "link": pdf_url,
                    "source": "OpenAlex",
                    "year": item.get('publication_year'),
                    "author": first_author,
                    "abstract": abstract_text
                })
                
                if len(papers) >= target_count: break
            
            current_page += 1
            
        except Exception as e:
            print(f"Error: {e}")
            break

    return papers[:target_count]

```

### 3. Integration Logic

Modify the main `run_omni_search` function in `1_search_omni.py`.

* **Priority:** Call `search_openalex` *first*.
* **Fallback:** Only call Semantic Scholar if OpenAlex returns fewer papers than `target_count`.
* **Deprecation:** Remove or comment out the old Crossref + ThreadPoolExecutor logic to clean up the code.

### 4. Self-Validation Protocol (Critical)

You must ensure this script works independently before we integrate it into the web app. Add a `if __name__ == "__main__":` block at the bottom of the file that performs the following "Smoke Test":

1. **Run a Test Search:** Search for the topic "Generative AI" with a target of 5 papers.
2. **Validate Links:** For each returned paper, perform a `requests.head()` check on the PDF link to verify it returns `200 OK`.
3. **Validate Abstracts:** Verify that the `abstract` field is not empty and contains readable text (length > 50 chars).
4. **Report:** Print a formatted report to the console showing:
* Total Papers Found
* Valid Link Count
* Valid Abstract Count
* Average Search Time



**Example Validation Output:**

```text
--- SELF-DIAGNOSTIC REPORT ---
✅ Search Complete: 0.8s
✅ Papers Found: 5/5
✅ Link Health: 5/5 (200 OK)
✅ Abstract Reconstruction: 5/5 Valid
------------------------------

```

**Expected Outcome:**
Provide the updated full code for `1_search_omni.py` that includes the OpenAlex search, the integration logic, and the self-validation block.