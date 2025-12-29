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

# Load environment variables
# Load environment variables (Force override to prevent stale shell keys)
load_dotenv(override=True)

def clean_json_string(s):
    """Helper to clean markdown formatting from JSON string."""
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    if s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()

def sanitize_folder_name(name):
    """Sanitizes category names for file system compatibility."""
    clean = "".join([c if c.isalnum() or c in (' ', '_', '-') else '' for c in name])
    return clean.strip().replace(' ', '_')

def get_best_model():
    """Dynamically finds the best available Flash model (matches Phase 1 logic)."""
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'flash' in m.name.lower():
                available_models.append(m.name)
        
        if not available_models: return 'models/gemini-pro'
        
        available_models.sort()
        # Prefer 1.5-flash if 2.0 is causing issues, or stick to auto-latest?
        # User asked to match Phase 1. Phase 1 picks the LAST sorted item.
        best_model = available_models[-1]
        print(f"Selected Model: {best_model}", flush=True)
        return best_model
    except:
            return 'models/gemini-1.5-flash'

def cluster_and_categorize(topic, sort_method="Most Relevant", limit=100, no_llm=False):
    print("=== Phase 3: The Smart Architect (Improved Clustering) ===", flush=True)
    print(f"Topic: {topic}")
    print(f"Prioritize By: {sort_method}, Limit: {limit}", flush=True)
    
    csv_path = "research_catalog.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
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
            
    # --- LIMITING LOGIC ---
    if len(df) > limit:
        print(f"Trimming {len(df)} papers to top {limit} for AI processing...")
        df = df.head(limit)
    
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
        
        papers_payload = []
        for index, row in df.iterrows():
            # Use DOI as robust ID. Fallback to Title if DOI missing (unlikely with strict filter)
            paper_id = row['DOI'] if pd.notna(row['DOI']) and str(row['DOI']).strip() else row['Title']
            papers_payload.append({
                "id": paper_id,
                "title": row['Title'],
                "description": str(row['Description'])[:500]
            })

        num_papers = len(df)
        if num_papers < 10:
            cat_count_msg = "2-3 broad categories"
        elif num_papers < 30:
            cat_count_msg = "3-5 distinct categories"
        else:
            cat_count_msg = "5-8 distinct categories"

        model_name = get_best_model()
        print(f"Consulting {model_name} to generate taxonomy...", flush=True)
        
        prompt = f"""
        You are an expert academic librarian organizing a library on the topic: "{topic}".
        Input: {num_papers} academic papers.
        Task:
        1. **Filter**: Review abstracts. If a paper is NOT primarily about "{topic}" or is generic junk, assign "DISCARD".
        2. **Cluster**: Group the remaining papers into {cat_count_msg}.
        
        Critical Constraints:
        1. **No Redundancy**: Do NOT use the words "{topic}" in the category names.
        2. **Consolidation**: Merge similar topics.
        3. **Cluster Size**: Every category MUST contain at least 2 papers.
        
        Output Format:
        Return strictly a JSON object. 
        KEYS = The exact "id" provided in the input (DOI). VALUES = Category Name.
        
        Papers:
        {json.dumps(papers_payload, indent=2)}
        """

        # Retry Loop for Phase 2
        model = genai.GenerativeModel(model_name)
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = model.generate_content(prompt)
                if response.text:
                    cleaned_response = clean_json_string(response.text)
                    taxonomy_map = json.loads(cleaned_response)
                    ai_success = True
                    print("Taxonomy generated successfully.", flush=True)
                    break
            except Exception as e:
                 if "429" in str(e) or "429" in getattr(e, 'message', ''):
                    wait = 60 # Fixed 60s wait (RPM reset window)
                    print(f"⚠️ Quota Exceeded (Attempt {attempt+1}/{max_retries}). Waiting {wait}s...")
                    time.sleep(wait)
                 else:
                    print(f"❌ AI Processing Failed: {e}")
                    ai_success = False
                    break
        
        if not ai_success:
             print(">> Falling back to single folder structure.")

    # 3. Post-Processing / Fallback Assignment
    if ai_success:
        # Enforce Orphan Rules
        counts = Counter([cat for cat in taxonomy_map.values() if cat != "DISCARD"])
        orphans = [cat for cat, count in counts.items() if count < 2]
        if orphans:
            general_cat = "General_Research"
            for doc_id, cat in taxonomy_map.items():
                if cat in orphans:
                    taxonomy_map[doc_id] = general_cat
    else:
        # Fallback Mode
        pass

    # 4. Organization
    df['Topic'] = topic
    topic_sanitized = sanitize_folder_name(topic)
    library_topic_root = f"./Library/{topic_sanitized}"
    os.makedirs(library_topic_root, exist_ok=True)
    
    categories_found = set()
    rows_to_drop = []
    df['Directory_Path'] = None

    for index, row in df.iterrows():
        # Robust Lookup: Try DOI first, then Title logic if needed (but DOI is primary)
        paper_id = row['DOI'] if pd.notna(row['DOI']) and str(row['DOI']).strip() else row['Title']
        
        # Check taxonomy map
        category = "General_Collection"
        if ai_success:
            category = taxonomy_map.get(paper_id, "General_Collection")
            
        if category == "DISCARD":
            rows_to_drop.append(index)
            continue
        
        df.at[index, 'Category'] = category
        categories_found.add(category)
        
        safe_category = sanitize_folder_name(category)
        dir_path = os.path.join(library_topic_root, safe_category)
        os.makedirs(dir_path, exist_ok=True)
        df.at[index, 'Directory_Path'] = dir_path

    if rows_to_drop:
        df = df.drop(rows_to_drop)
        print(f"Rejected {len(rows_to_drop)} off-topic papers.")

    output_csv = "research_catalog_categorized.csv"
    df.to_csv(output_csv, index=False)
    
    print("\n=== Categorization Complete ===")
    if ai_success:
        print(f"AI Organized into {len(categories_found)} Categories.")
    else:
        print("Fallback Mode: Papers saved to 'General_Collection'.")
        
    print(f"Structure ready in '{library_topic_root}/'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Architect: Cluster and Filter Papers")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--sort", default="Most Relevant")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--no_llm", action="store_true")
    args = parser.parse_args()
    
    cluster_and_categorize(args.topic, args.sort, args.limit, args.no_llm)

