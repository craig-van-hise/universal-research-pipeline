import pandas as pd
import google.generativeai as genai
import os
import json
from dotenv import load_dotenv
import time
import re
import argparse
import shutil
from collections import Counter
import sys
import typing_extensions

# Load environment variables
# Load environment variables (Force override to prevent stale shell keys)
load_dotenv(override=True)

class PaperClassification(typing_extensions.TypedDict):
    id: str
    category_name: str
    justification_quote: str  # Forces the LLM to prove its work

class TaxonomyResponse(typing_extensions.TypedDict):
    assignments: list[PaperClassification]

def sanitize_folder_name(name):
    """Sanitizes category names for file system compatibility."""
    clean = "".join([c if c.isalnum() or c in (' ', '_', '-') else '' for c in name])
    return clean.strip().replace(' ', '_')

def clean_json_string(json_str):
    """
    Cleans common JSON formatting errors from LLM output.
    1. Removes Markdown code fences (```json, ```).
    2. Escapes unescaped newlines inside strings.
    3. Trims whitespace.
    """
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    if json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()





def get_best_model():
    """Dynamically finds the best available Flash model."""
    try:
        available_models = []
        for m in genai.list_models():
            # Filter for generation models with 'flash' in name
            if 'generateContent' in m.supported_generation_methods and 'flash' in m.name.lower():
                available_models.append(m.name)
        
        if not available_models: 
            return 'models/gemini-pro' # Fallback if no flash
        
        available_models.sort()
        # Phase 1 logic picks the last one (usually latest)
        best_model = available_models[-1]
        print(f"Selected Model: {best_model}", flush=True)
        return best_model
    except:
        return 'models/gemini-1.5-flash'

def cluster_and_categorize(topic, sort_method="Most Relevant", limit=100, no_llm=False, use_keywords=False):
    print("=== Phase 3: The Smart Architect (Improved Clustering) ===", flush=True)
    print(f"Topic: {topic}")
    print(f"Prioritize By: {sort_method}, Limit: {limit}", flush=True)
    

        
    # --- AUTOMATED CLEANUP ---

        

    csv_filename = "research_catalog.csv"
    data_dir_csv = os.path.join(os.path.dirname(__file__), "../data", csv_filename)
    
    if os.path.exists(csv_filename):
        csv_path = csv_filename
    elif os.path.exists(data_dir_csv):
        csv_path = data_dir_csv
    else:
        print(f"Error: {csv_filename} not found in CWD or ../data/")
        return
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # 1. Pre-Processing
    initial_count = len(df)
    df = df[df['Title'].str.len() > 15] 
    df = df[~df['Title'].str.lower().isin(['audio', 'spatial audio', 'introduction', 'front matter', 'back matter', 'index'])]
    
    # --- SORTING LOGIC ---
    if sort_method in ["Date: Newest", "Date: Oldest"]:
        # Ensure date format
        df['Publication_Date'] = pd.to_datetime(df['Publication_Date'], errors='coerce')
        
        if sort_method == "Date: Newest":
            print("Sorting papers by Date (Newest First)...")
            df = df.sort_values(by='Publication_Date', ascending=False)
        else: # Oldest
            print("Sorting papers by Date (Oldest First)...")
            df = df.sort_values(by='Publication_Date', ascending=True)
            
    # --- LIMITING LOGIC (BUFFERED) ---
    # We buffer input to AI because some papers might be DISCARDED.
    # User calls this "Musical Chairs". We need to ensure we have enough valid papers left.
    # Buffer Strategy: Double the limit or add 50, whichever is safer.
    process_limit = max(limit * 2, limit + 50)
    if len(df) > process_limit:
        print(f"Trimming {len(df)} papers to {process_limit} for AI processing (Buffer included)...")
        df = df.head(process_limit)
    
    print(f"Loaded {len(df)} valid papers from catalog.")

    if df.empty:
        print("No valid papers to categorize.")
        return

    # 2. AI Categorization Logic
    api_key = os.getenv("GOOGLE_API_KEY")
    taxonomy_map = {}
    ai_success = False

    if not api_key or no_llm:
        if no_llm: print("⚠️ AI Disabled by --no_llm flag.")
        else: print("⚠️ No Google API Key found. Skipping AI Categorization.")
        print(">> Falling back to single folder structure.")
    else:

        # Valid API Key case (Standardized Init)
        genai.configure(api_key=api_key)
        
        # Valid API Key case (Standardized Init)
        genai.configure(api_key=api_key)
        
        # Get unique verticals (handles case where column might be missing)
        if 'Search_Vertical' not in df.columns:
            df['Search_Vertical'] = 'Unsorted'
        unique_verticals = df['Search_Vertical'].unique()
        print(f"DEBUG: Processing {len(unique_verticals)} Keyword Groups for Taxonomy...", flush=True)

        for vertical in unique_verticals:
            print(f"\n   -> Analyzing Group: '{vertical}'...", flush=True)
            v_df = df[df['Search_Vertical'] == vertical]
            
            if v_df.empty: continue

            # Create Payload for this vertical
            papers_payload = []
            for index, row in v_df.iterrows():
                # Use DOI as robust ID
                paper_id = row['DOI'] if pd.notna(row['DOI']) and str(row['DOI']).strip() else row['Title']
                
                # Data Hygiene: Filter short/bad abstracts
                desc = str(row['Description'])
                if len(desc) < 50:
                     desc = f"Title: {row['Title']}" # Force Title-only categorization
                     
                papers_payload.append({
                    "id": paper_id,
                    "title": row['Title'],
                    "description": desc[:500]
                })

            num_papers_v = len(v_df)
            
            # --- Logic for Small Groups ---
            if num_papers_v < 6:
                print(f"      Small group ({num_papers_v} papers). Assigning to '{vertical} Overview'.")
                for p in papers_payload:
                    taxonomy_map[p['id']] = f"{vertical} Overview"
                continue # Skip LLM

            # --- Logic for Large Groups (LLM) ---
            # Dynamic prompt constraints based on group size
            if num_papers_v < 20:
                 target_cats = "exactly 2"
                 density_note = f"roughly {int(num_papers_v/2)} papers"
            elif num_papers_v < 60:
                 target_cats = "exactly 4"
                 density_note = f"roughly {int(num_papers_v/4)} papers"
            else:
                 target_cats = "5-8"
                 density_note = "balanced distribution"

            model_name = get_best_model()

            prompt = f"""
            You are an expert academic librarian organizing a specific sub-folder of papers on: "{vertical}" (Topic: {topic}).
            Input: {num_papers_v} academic papers.
            
            Task:
            1. **Analyze**: Identify **{target_cats}** distinct technical themes within this specific sub-field.
            2. **Assign**: Assign EVERY paper to one of these themes.
            3. **Filter**: If a paper is unrelated to "{vertical}", assign "DISCARD".
            4. **Proof**: For every assignment, you MUST quote a specific phrase from the abstract that justifies your choice.
            
            Critical Constraints:
            1. **Style**: Format category names as **concise Noun Phrases** (e.g., 'Spatial Audio', not 'Papers about Spatial Audio'). Avoid parenthetical qualifiers.
            2. **Context**: These papers are ALREADY filtered by keyword "{vertical}". Do NOT create a category named "{vertical}". Break it down further (e.g. if "{vertical}"="HRTF", use "HRTF Measurement", "HRTF Personalization").
            3. **Broad Clusters**: Do NOT map 1-to-1.
            4. **Forbidden**: "General", "Miscellaneous", "Other".
            5. **Density**: Each theme should have {density_note}.
            
            Papers:
            {json.dumps(papers_payload, indent=2)}
            """

            # Retry Loop (Per Vertical)
            model = genai.GenerativeModel(model_name)
            local_success = False
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.GenerationConfig(
                            response_mime_type="application/json",
                            response_schema=TaxonomyResponse
                        )
                    )
                    
                    if response.text:
                        # Direct JSON parse of the structured output
                        cleaned_text = clean_json_string(response.text)
                        payload = json.loads(cleaned_text)
                        
                        # Process assignments
                        local_map = {}
                        print(f"      Mapped {len(payload.get('assignments', []))} papers:")
                        
                        for item in payload.get('assignments', []):
                            pid = item['id']
                            cat = item['category_name']
                            # 1. Take the full name from the LLM
                            cat_raw = item['category_name'].strip()

                            # 2. Safety Truncate: Only chop if excessively long (> 6 words)
                            words = cat_raw.split()
                            if len(words) > 6:
                                cat_raw = " ".join(words[:6])

                            # 3. Stopword Cleanup: Remove trailing connectors
                            # Regex targets: and, or, of, the, for, in, on, with, to
                            cat = re.sub(r'[^a-zA-Z0-9]+$', '', cat_raw) # Strip non-alphanumeric (brackets, punctuation)
                            cat = re.sub(r'\s+(and|or|of|the|for|in|on|with|to)$', '', cat, flags=re.IGNORECASE).strip()
                                
                            quote = item.get('justification_quote', 'No Quote provided')
                            local_map[pid] = cat
                            
                            # Sanity Check Log
                            # Only print first 3 to avoid spamming console, or print all if verbose? 
                            # Let's print all for now as requested by user to "see why"
                            print(f"       [{cat}] <- \"{quote[:60]}...\"")

                        taxonomy_map.update(local_map)
                        local_success = True
                        print(f"      Refined into {len(set(local_map.values()))} categories.", flush=True)
                        break
                except Exception as e:
                     if "429" in str(e):
                        time.sleep(10) # 429 backoff
                     elif attempt == max_retries - 1:
                        print(f"      ❌ Failed to categorize '{vertical}': {e}")

            if not local_success:
                 # Fallback for this vertical ONLY
                 print(f"      Falling back to '{vertical} Overview'.")
                 for p in papers_payload:
                     taxonomy_map[p['id']] = f"{vertical} Overview"

            time.sleep(2) # Rate limit hygiene

        if len(taxonomy_map) > 0:
            ai_success = True
        else:
             print(">> Global AI Failure: No categories generated.")


    # Debug: Print Raw Categories
    if ai_success:
        raw_counts = Counter(taxonomy_map.values())
        print("DEBUG RAW AI CATEGORIES:")
        for k, v in raw_counts.items():
            print(f"   '{k}': {v}")
            
    # 3. Post-Processing / Fallback Assignment
    if ai_success:
        # Enforce Orphan Rules
        # New Logic: No Orphan Reassignment
        # We accept singleton categories to prevent "Miscellaneous" bloating.
        counts = Counter(taxonomy_map.values())
        print(f"DEBUG: Category Distribution: {counts}") 
        
        # 1. Map current AI categories to the DataFrame
        mapped_count = 0
        total_rows = len(df)
        for idx, row in df.iterrows():
             pid = row['DOI'] if pd.notna(row['DOI']) and str(row['DOI']).strip() else row['Title']
             cat = taxonomy_map.get(pid, "Miscellaneous")
             if cat != "Miscellaneous": mapped_count += 1
             df.at[idx, '_Temp_Cat'] = cat
        
        print(f"DEBUG: Mapped {mapped_count}/{total_rows} papers to categories. (Rest are Miscellaneous)")
    else:
        # Fallback Mode
        pass

    # 4. Organization
    df['Topic'] = topic
    
    # Base Root (Topic Level)
    topic_sanitized = sanitize_folder_name(topic)
    base_library_root = os.path.join("./ScholarStack", topic_sanitized)
    
    categories_found = set()
    rows_to_drop = []
    df['Directory_Path'] = None

    for index, row in df.iterrows():
        # Robust Lookup
        paper_id = row['DOI'] if pd.notna(row['DOI']) and str(row['DOI']).strip() else row['Title']
        
        # Check taxonomy map
        category = "Miscellaneous"
        if ai_success:
            category = taxonomy_map.get(paper_id, "Miscellaneous")
            
        if category == "DISCARD":
            rows_to_drop.append(index)
            continue
        
        df.at[index, 'Category'] = category
        categories_found.add(category)
        
        # Construct Path
        safe_category = sanitize_folder_name(category)
        
        # Logic: <Topic>/<Keyword?>/<Category>
        # Logic: <Topic>/<Keyword?>/<Category>
        current_root = base_library_root
        
        # Use Keywords as Sub-folders?
        if use_keywords:
            raw_vertical = row.get('Search_Vertical', 'Unsorted')
            safe_vertical = sanitize_folder_name(str(raw_vertical))
            
            # If the keyword IS the topic, put it in a general folder so it doesn't clutter root
            # But generally, we treat the Search Vertical as the Level 2 folder.
            if safe_vertical.lower() == topic_sanitized.lower():
                 current_root = os.path.join(base_library_root, "_General")
            else:
                 current_root = os.path.join(base_library_root, safe_vertical)
        
        # Determine Final Directory
        # Logic: current_root is now <Topic>/<Keyword> (or <Topic> if not using keywords)
        # We ALWAYS append the Category.
        # User explicitly requested strict "Library/Topic/Keyword/Category".
        
        dir_path = os.path.join(current_root, safe_category)
            
        os.makedirs(dir_path, exist_ok=True)
        df.at[index, 'Directory_Path'] = dir_path

    if rows_to_drop:
        print(f"\n--- 🗑️ Rejected Papers Audit ({len(rows_to_drop)}) ---")
        for idx in rows_to_drop:
            print(f"   [Discarded] {df.loc[idx, 'Title']}")
        print("------------------------------------------\n")
        
        df = df.drop(rows_to_drop)
        print(f"Rejected {len(rows_to_drop)} off-topic papers.")

    # --- FINAL TRIM TO EXACT LIMIT ---
    # Now that we've filtered, strictly enforce the user limit
    if len(df) > limit:
         print(f"Final Count {len(df)} > Requested {limit}. Trimming excess to match quota.")
         df = df.head(limit)

    output_csv = "research_catalog_categorized.csv"
    df.to_csv(output_csv, index=False)
    
    print("\n=== Categorization Complete ===")
    if ai_success:
        print(f"AI Organized into {len(categories_found)} Categories.")
    else:
        print("Fallback Mode: Papers saved to 'Miscellaneous'.")
        
    print(f"Structure ready in '{base_library_root}/'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Architect: Cluster and Filter Papers")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--sort", default="Most Relevant")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--no_llm", action="store_true")
    parser.add_argument("--use_keywords", action="store_true")
    args = parser.parse_args()
    
    cluster_and_categorize(args.topic, args.sort, args.limit, args.no_llm, args.use_keywords)

