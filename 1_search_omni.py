import argparse
import time
import json
import pandas as pd
import requests
import arxiv
from semanticscholar import SemanticScholar
from unpywall import Unpywall
from tqdm import tqdm
import os
import re
from urllib.parse import urlparse
import datetime
from dotenv import load_dotenv
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import fitz  # PyMuPDF

# --- Suppress Warnings (Must be before imports that trigger them) ---
warnings.filterwarnings("ignore")
os.environ["GRPC_VERBOSITY"] = "ERROR" # Silence Google GRPC warnings

# Load Environment
# Load Environment (Force Override to ignore stale shell vars)
load_dotenv(override=True)

# Check for Google API
# Check for Google API
try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# Robust Request Session
def get_session():
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def reconstruct_abstract(inverted_index):
    if not inverted_index: return ""
    max_index = max(max(pos) for pos in inverted_index.values())
    words = [""] * (max_index + 1)
    for word, positions in inverted_index.items():
        for pos in positions: words[pos] = word
    return " ".join(words)

class ResearchCrawler:
    def __init__(self, topic, keywords, author, publication, date_start, date_end, count, sites, keyword_logic='any', no_llm=False):
        self.keyword_logic = keyword_logic if keyword_logic else 'any'
        self.no_llm = no_llm
        
        self.offsets = {'semantic': 0, 'arxiv': 0}
        if os.path.exists("research_catalog.csv"):
            try: os.remove("research_catalog.csv")
            except: pass

        self.raw_topic = topic
        raw_keywords = [k.strip() for k in keywords.split(',')] if keywords else []
        self.keywords_list = list(raw_keywords)
        self.author = author
        self.publication = publication
        
        self.date_start = date_start
        self.date_end = date_end
        self.year_start = int(date_start[:4]) if date_start else 2000
        self.year_end = int(date_end[:4]) if date_end else 2030
        
        self.final_target_count = int(count)
        # Buffer: Fetch 5x what user asked for to allow for high-quality filtering
        self.target_count = int(self.final_target_count * 5.0) 
        
        self.sites = sites if sites else ['all']
        self.results = []
        self.seen_dois = set()
        self.seen_titles = set()
        self.seen_ids = set()
        
        self.session = get_session()
        self.keyword_logic = keyword_logic if keyword_logic else 'any'
        
        self.offsets = {'semantic': 0, 'arxiv': 0}

    def _normalize_date(self, date_str):
        if not date_str: return f"{self.year_start}/01/01"
        try:
            if re.match(r'^\d{4}$', str(date_str)): return f"{date_str}/01/01"
            return str(date_str).replace('-', '/')
        except: return f"{self.year_start}/01/01"

    def _is_date_in_range(self, date_str):
        try:
            d = datetime.datetime.strptime(self._normalize_date(date_str), "%Y/%m/%d").date()
            start = datetime.datetime.strptime(self.date_start, "%Y-%m-%d").date() if self.date_start else None
            end = datetime.datetime.strptime(self.date_end, "%Y-%m-%d").date() if self.date_end else None
            if start and d < start: return False
            if end and d > end: return False
            return True
        except: return True

    def _parse_filename(self, url):
        if not url: return 'Pending_Header_Check'
        path = urlparse(url).path
        filename = os.path.basename(path)
        if filename and (filename.lower().endswith('.pdf') or 'pdf' in url.lower()):
            if not filename.lower().endswith('.pdf'): return filename + ".pdf"
            return filename
        return 'Pending_Header_Check'

    def _validate_full_text(self, pdf_content, keywords):
        """
        Robust Front-Matter Audit:
        Scans first ~2 pages. Ignores 'Movie' annotations to prevent crashes.
        """
        try:
            # 1. Open Document (from bytes)
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            text_block = ""
            
            # 2. Limit to First 2 Pages (Front-Matter)
            for i in range(min(2, doc.page_count)):
                page = doc.load_page(i)
                # Use 'text' mode with flags to be robust
                # PRP 9.9.5: Added MEDIABOX_CLIP to avoid reading hidden/cropped text
                text_block += page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_DEHYPHENATE | fitz.TEXT_MEDIABOX_CLIP) + " "
            
            doc.close()
            
            # 3. Fuzzy Regex Check
            blob = text_block.lower()
            
            for k in keywords:
                # Fuzzy Regex Construction
                clean_k = k.replace('"', '').strip().lower()
                fuzzy_k = clean_k.replace(" ", r"[\s\-]*")
                if "crosstalk" in clean_k:
                    fuzzy_k = fuzzy_k.replace("crosstalk", r"cross[\s\-]*talk")
                
                pattern = fuzzy_k + r"s?" 
                
                if re.search(pattern, blob):
                    return True, f"Found match for '{clean_k}'"
                    
            return False, "No keywords found in Front-Matter"
            
        except RuntimeError as e:
            # PRP 9.9.5: Catch specific MuPDF RuntimeErrors (e.g. 'syntax error')
            return False, f"PDF Runtime Logic Error: {e}"
        except Exception as e:
            # Catch general errors
            return False, f"PDF Audit Skipped: {e}"

    def _pre_filter(self, title, date, doi):
        if not self._is_date_in_range(date): return False, "Date out of range"
        
        # Deduplication Check
        if doi and doi in self.seen_dois: return False, "Duplicate DOI"
        
        norm_title = re.sub(r'[^a-z0-9]', '', str(title).lower())
        if norm_title in self.seen_titles: return False, "Duplicate Title"
        
        return True, "Passed"

    def _check_and_download_pdf(self, url, doi):
        """
        Downloads PDF, validates Full Text, and returns (Success, ContentOrUrl)
        """
        if not url: 
            if doi:
                try:
                    res = Unpywall.doi(doi)
                    if res and res.best_oa_location and res.best_oa_location.url:
                        url = res.best_oa_location.url
                except: return False, None
        
        if not url: return False, None
            
        try:
            check_session = requests.Session()
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            # Stream download to avoid memory issues with huge files
            r = check_session.get(url, headers=headers, timeout=15)
            
            if r.status_code == 200 and b'%PDF' in r.content[:1024]:
                # --- STRICT FULL TEXT GATE ---
                # Check directly in memory before saying "Success"
                verify_terms = self.keywords_list if self.keywords_list else [self.raw_topic]
                is_valid, reason = self._validate_full_text(r.content, verify_terms)
                
                if is_valid:
                    return True, url 
                else:
                    # print(f"DEBUG: Rejected {url} (Text Audit Failed: {reason})")
                    return False, None
            
            return False, None
        except Exception:
            return False, None

    def _process_batch(self, candidates):
        """
        Refactored Validation (PRP 9.9.9.1):
        1. Deduplicate (Global seen_ids).
        2. Audit Metadata (Title/Abstract/Keywords).
        3. If keyword found OR inferred by search -> Accept.
        4. PDF Download happens LATER (decoupled).
        """
        # Fuzzy regex for the keyword
        primary_key = self.keywords_list[0].replace('"', '').lower()
        fuzzy_pattern = re.sub(r's?\s+', r'[\\s\\-]*', primary_key) + r's?'
        
        print(f"DEBUG: Processing batch of {len(candidates)} candidates...", flush=True)
        
        for c in candidates:
            # 1. Global Deduplication
            if c['id'] in self.seen_ids:
                continue
            self.seen_ids.add(c['id'])
            
            # 2. Construct Audit Blob
            # We use the pre-parsed 'description' (abstract) and 'keywords' from execute_openalex_query
            audit_blob = f"{c['title']} {c['description']} {c['keywords']}".lower()
            
            # 3. The Logic Check
            match_found = re.search(fuzzy_pattern, audit_blob)
            
            # Set final_url to the source url since we aren't validating it yet
            c['final_url'] = c['url']
            
            if match_found:
                # print(f"   [Accepted] {c['title'][:60]}...")
                self._add_final_result(c)
            else:
                # 4. The Safety Net (Inferred Acceptance)
                # print(f"   [Accepted (Inferred)] {c['title'][:60]}...")
                self._add_final_result(c)
                
            # Stop if global target met
            if len(self.results) >= self.target_count:
                break

    def _add_final_result(self, c):
        # Add to tracking sets immediately to prevent race-condition duplicates
        if c['doi']: self.seen_dois.add(c['doi'])
        norm_title = re.sub(r'[^a-z0-9]', '', str(c['title']).lower())
        self.seen_titles.add(norm_title)

        self.results.append({
            'Title': c['title'].strip(),
            'Authors': c['authors'],
            'Original_Filename': self._parse_filename(c['final_url']),
            'Publication_Date': self._normalize_date(c['date']),
            'Category': 'Unsorted',
            'Description': c['description'][:3000] + "..." if c['description'] and len(c['description']) > 3000 else c['description'],
            'Is_Paywalled': False,
            'Is_Downloaded': False,
            'Source_URL': c['final_url'],
            'DOI': c['doi'],
            '_Source': c['source_name']
        })
        print(f"[Accepted] {c['title'][:60]}...", flush=True)

    def resolve_concept_id(self, topic_name):
        return self.resolve_entity_id('concepts', topic_name)

    # ... (skipping unchanged helper methods) ...
    def llm_map_to_openalex_entity(self, user_query):
        """Asks Gemini to map colloquial terms to official OpenAlex Concept Names."""
        client = self.get_genai_client()
        if not client: return None
        
        prompt = (f"What is the single most likely official OpenAlex Concept Name "
                  f"that corresponds to the research topic '{user_query}'? "
                  f"Return ONLY the concept name. Examples: 'Heart Attack' -> 'Myocardial infarction', "
                  f"'Spatial Audio' -> '3D audio'.")
        try:
            models_to_try = ['gemini-2.0-flash-001', 'gemini-2.0-flash-lite-001', 'gemini-2.0-flash']
            for attempt in range(3):
                for model in models_to_try:
                    try:
                        resp = client.models.generate_content(model=model, contents=prompt)
                        if resp.text:
                             predicted_name = resp.text.strip().replace('"', '').replace("'", "")
                             print(f"🧠 LLM Semantic Router: '{user_query}' -> '{predicted_name}'")
                             return predicted_name
                    except Exception as e:
                        if "429" in str(e) or "quota" in str(e).lower():
                            continue
                        raise e
                time.sleep((attempt + 1) * 2)
        except: pass
        return None

    def expand_keywords_with_llm(self, keywords):
        """Asks Gemini to generate high-quality synonyms for keywords."""
        if not keywords: return keywords
        client = self.get_genai_client()
        if not client: return keywords
        
        model_name = self.get_best_model(client)
        
        # Clean keywords first
        clean_keys = [k.replace('"', '').strip() for k in keywords]
        input_str = ", ".join(clean_keys)
        
        prompt = (f"Generate 3-4 scientific synonyms or related technical terms for: '{input_str}'. "
                  f"Focus on terms used in academic literature. "
                  f"Return strictly a comma-separated list. No explanations.")
        
        models_to_try = ['gemini-2.0-flash-001', 'gemini-2.0-flash-lite-001', 'gemini-2.0-flash']
        print(f"🧠 Expanding Synonyms for: [{input_str}]...")
        resp_text = self._query_llm_with_rotation(prompt)
        if resp_text:
            new_synonyms = [s.strip() for s in resp_text.split(',') if s.strip()]
            print(f"   -> Expansion: {new_synonyms}")
            return list(set(clean_keys + new_synonyms))

        return keywords

            
        return keywords

    def get_technical_synonyms_from_llm(self, titles, seed_keyword, user_topic):
        """
        Uses LLM to extract synonyms, using the User's Topic as a dynamic filter.
        """
        if not titles: return []
        client = self.get_genai_client()
        if not client: return []
        
        model_name = self.get_best_model(client)
        
        prompt = (
            f"CONTEXT: The user is researching '{user_topic}'. "
            f"The primary keyword is '{seed_keyword}'.\n"
            f"SOURCE DATA: Here are recent paper titles from a identified expert in this field:\n"
            f"{' | '.join(titles[:150])}\n\n"
            f"TASK: Identify 15 specific technical synonyms, acronyms, or method names for '{seed_keyword}' "
            f"that are used within the domain of '{user_topic}'.\n\n"
            f"RULES:\n"
            f"1. FILTER IRRELEVANCE: The expert may publish in other fields. IGNORE titles unrelated to '{user_topic}'.\n"
            f"2. PRECISION: If a term is broad (like 'Active Control'), qualify it to fit '{user_topic}' (e.g., 'Active Noise Control').\n"
            f"3. FORMAT: Return ONLY a comma-separated list of phrases (2-4 words). No full titles."
        )
        
        print(f"🧠 Synthesizing Expert Vocabulary from {len(titles)} titles (Guided by topic: '{user_topic}')...")
        resp_text = self._query_llm_with_rotation(prompt)

        if resp_text:
             # Basic cleanup
            raw_syns = [s.strip() for s in resp_text.split(',') if len(s.strip()) > 2]
            
            final_syns = []
            for s in raw_syns:
                # Enforce 2-4 word limit logic
                words = s.split()
                if len(words) > 5: continue 
                
                s_clean = s.replace('"', '').replace("'", "")
                final_syns.append(f'"{s_clean}"')
            
            final_syns = final_syns[:15]
            print(f"   -> LLM Suggested: {final_syns}")
            return final_syns
            
        return []

    def resolve_entity_id(self, entity_type, query):
        """Robustly resolves query to ID using deeper searches."""
        # 1. Direct Autocomplete
        try:
            r = self.session.get(f"https://api.openalex.org/autocomplete/{entity_type}", params={"q": query}, timeout=5)
            if r.status_code == 200 and r.json().get('results'):
                res = r.json()['results'][0]
                return res['id'].split('/')[-1]
        except: pass

        # 2. LLM Semantic Router
        if entity_type == 'concepts':
            semantic_name = self.llm_map_to_openalex_entity(query)
            if semantic_name:
                # Force a SEARCH for the semantic name with HIGHER PAGE LIMIT
                try:
                    r = self.session.get(f"https://api.openalex.org/{entity_type}", params={"search": semantic_name, "per-page": 5}, timeout=5)
                    if r.status_code == 200:
                        results = r.json().get('results', [])
                        if results:
                            # Iterate to find exact match or take top
                            for res in results:
                                if res['display_name'].lower() == semantic_name.lower():
                                    print(f"DEBUG: Found ID via LLM Match: {res['display_name']} ({res['id']})")
                                    return res['id'].split('/')[-1]
                            # Fallback to top result
                            return results[0]['id'].split('/')[-1]
                except: pass

        return None

    def execute_openalex_query(self, label, filters, search_query):
        """Helper to run a specific OpenAlex query strategy with strict quotas."""
        print(f"\n🔎 Executing Strategy: {label}")
        print(f"   Query: search='{search_query}' filter='{filters}'")
        
        base_url = "https://api.openalex.org/works"
        current_page = 1
        per_page = 200
        
        # Continuous loop until we meet quota OR exhaust results for this strategy
        while True:
            # Stop if global target met
            if len(self.results) >= self.target_count:
                print(f"✅ Target quota met ({len(self.results)} papers). Stopping.")
                return

            params = {
                "filter": filters,
                "per-page": per_page,
                "page": current_page,
                "select": "title,id,publication_year,open_access,authorships,abstract_inverted_index,doi,keywords,concepts"
            }
            if search_query: params["search"] = search_query

            try:
                r = self.session.get(base_url, params=params, timeout=10)
                if r.status_code != 200: break
                results = r.json().get('results', [])
                if not results: 
                    print(f"DEBUG: No more results from OpenAlex (Page {current_page}).")
                    break
                
                print(f"DEBUG: Parsing Page {current_page} ({len(results)} raw candidates)...")
                batch = []
                
                for item in results:
                    pdf_url = item.get('open_access', {}).get('oa_url')
                    if not pdf_url: continue # Skip closed access

                    abstract_text = reconstruct_abstract(item.get('abstract_inverted_index')) or ""
                    
                    keywords_list = [k.get('display_name', '') for k in item.get('keywords', [])]
                    keywords_text = " ".join(keywords_list)
                    
                    batch.append({
                        'id': item.get('id'),
                        'title': item.get('title', ""),
                        'authors': ", ".join([a.get("author", {}).get("display_name", "") for a in item.get('authorships', [])]),
                        'date': str(item.get('publication_year', '')),
                        'description': abstract_text,
                        'doi': item.get('doi', '').replace("https://doi.org/", ""),
                        'url': pdf_url, 
                        'source_name': 'OpenAlex',
                        'keywords': keywords_text
                    })
                
                # Trust-Based Validation (PRP 9.9.9.1)
                self._process_batch(batch)
                
                current_page += 1
                if current_page > 50: # Safety cap (10k papers per strategy)
                    break 
                
            except Exception as e: 
                print(f"Error in strategy {label}: {e}")
                break

    def get_genai_client(self):
        """Lazy loader for GenAI Client."""
        if self.no_llm: 
            # print("DEBUG: LLM Disabled by user flag.", flush=True)
            return None
        if not HAS_GENAI or not os.getenv("GOOGLE_API_KEY"): return None
        return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    def get_best_model(self, client):
        """Returns the best available Flash model."""
        # Hardcoded for stability and quota optimization
        return 'gemini-2.0-flash-001'

    def _query_llm_with_rotation(self, prompt, context_label="Generic"):
        """
        Unified LLM Query Handler.
        Strict Compliance: NO Rotation. NO Dismissal.
        Persistently attempts to query 'gemini-2.0-flash-001' with backoff.
        """
        if self.no_llm: return None

        key = os.getenv("GOOGLE_API_KEY")
        if not key: 
            print("❌ DEBUG: No API Key found in env!")
            return None
        
        print(f"🔑 DEBUG: Using Key: {key[:5]}...{key[-3:]}")

        client = self.get_genai_client()
        if not client: return None

        # User forbidden rotation: Stick to the best model.
        target_model = 'gemini-2.0-flash-001'
        
        # Persistence Loop
        for attempt in range(1, 4):
            try:
                resp = client.models.generate_content(model=target_model, contents=prompt)
                if resp.text:
                    return resp.text
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str:
                    wait_time = attempt * 10
                    print(f"      ⚠️ Quota Hit on {target_model}. Waiting {wait_time}s... (Attempt {attempt}/3)")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"      ⚠️ API Error on {target_model}: {e}")
                    # Non-quota errors might be fatal to this request, but we don't kill the LLM.
                    return None
        
        print(f"      ❌ LLM Failed after 3 retries. Returning None for this request.")
        return None

        print(f"🧠 Expanding Topic Scope for: '{topic}'...")
        resp_text = self._query_llm_with_rotation(prompt)
        
        if resp_text:
            new_topics = [t.strip() for t in resp_text.split(',') if t.strip()]
            print(f"   -> Expansion: {new_topics}")
            return list(set([topic] + new_topics))

        return [topic]

    def get_search_verticals_from_llm(self, topic):
        """Generates list of search verticals using model rotation."""
        print("   🧠 Defining Search Verticals with LLM...")
        verticals = [topic]
        
        prompt = (
            f"The user is researching '{topic}'. Identify the 8 most distinct, high-yield 'Search Verticals' "
            f"for finding papers in this field. \n"
            f"INSTRUCTIONS:\n"
            f"1. Include Broad Synonyms (e.g., if topic is Spatial Audio -> '3D Audio', 'Immersive Audio')\n"
            f"2. Include Core Sub-disciplines (e.g., 'Binaural', 'Ambisonics', 'Wave Field Synthesis')\n"
            f"3. Return ONLY a comma-separated list of 8 terms."
        )
        
        resp_text = self._query_llm_with_rotation(prompt)
        if resp_text:
            raw_response = resp_text
            llm_verticals = [s.strip().replace('"', '') for s in raw_response.split(',') if len(s.strip()) > 3]
            if llm_verticals:
                return llm_verticals
        
        print("   ⚠️ LLM Verticals failed or disabled. Using default.")
        return verticals

    def search_via_iterative_loop(self):
        """
        STRATEGY: Divide and Conquer (PRP 9.9.9).
        Runs separate, targeted searches for distinct sub-fields to maximize recall 
        and bypass OpenAlex query complexity limits.
        """
        clean_keyword = self.keywords_list[0].replace('"', '')
        print(f"\n🚀 STARTING ITERATIVE LOOP SEARCH for: '{self.raw_topic}' + '{clean_keyword}'")
        
        # --- STEP 1: GENERATE SEARCH VERTICALS ---
        print("   🧠 Defining Search Verticals with LLM...")
        
        verticals = [self.raw_topic] # Default
        

        
        
        verticals = self.get_search_verticals_from_llm(self.raw_topic)
        # Ensure the user's raw topic is always the first loop
        if self.raw_topic not in verticals:
            verticals.insert(0, self.raw_topic)
            
        # Limit to 8 to respect quotas/time
        verticals = verticals[:8]
        print(f"   ✅ Targeted Verticals: {verticals}", flush=True)

        # --- STEP 2: EXECUTE LOOP ---
        for vertical in verticals:
            print(f"\n   🔄 Loop: ('{clean_keyword}') AND ('{vertical}')", flush=True)
            
            # Construct simple, high-power query
            query = f'("{clean_keyword}") AND ("{vertical}")'
            
            # Execute standard query 
            # Note: The execute_openalex_query method handles PDF downloading and Deduplication internally.
            filters = ["is_oa:true", "has_doi:true", "type:article|conference-paper"]
            if self.date_start: filters.append(f"publication_year:>{self.year_start-1}")
            if self.date_end: filters.append(f"publication_year:<{self.year_end+1}")
            filter_str = ",".join(filters)
            
            self.execute_openalex_query(f"Vertical: {vertical}", filter_str, query)
            
            # Stop if global target met (checked inside execute_openalex_query too, but good to check here)
            if len(self.results) >= self.target_count:
                break
                
        print(f"\n   🏁 Iterative Loop Complete. Final Catalog Size: {len(self.results)}")

    def search_openalex_text_fallback(self):
        """Standard fallback if backdoor fails."""
        print("🔍 Executing Standard Text Fallback...")
        filters = ["is_oa:true", "has_doi:true", "type:article|conference-paper"]
        if self.date_start: filters.append(f"publication_year:>{self.year_start-1}")
        if self.date_end: filters.append(f"publication_year:<{self.year_end+1}")
        filter_str = ",".join(filters)
        
        clean_keywords = [k.replace('"', '') for k in self.keywords_list]
        key_part = " OR ".join([f'"{k}"' for k in clean_keywords]) 
        query_str = f'("{self.raw_topic}") OR ({key_part})' if self.keywords_list else f'"{self.raw_topic}"'
        
        self.execute_openalex_query("Fallback: Text Search", filter_str, query_str)

    def search_arxiv(self):
        # Fallback only
        pass 
    
    def search_semantic_scholar(self):
        # Fallback only
        pass

    def save_results(self):
        df = pd.DataFrame(self.results)
        if not df.empty:
            # Deduplicate by Title and DOI
            df['norm_title'] = df['Title'].apply(lambda x: re.sub(r'[^a-z0-9]', '', str(x).lower()) if x else '')
            df = df.drop_duplicates(subset=['norm_title'])
            df = df.drop_duplicates(subset=['DOI'])
            df = df.drop(columns=['norm_title'], errors='ignore')
            
            df.to_csv("research_catalog.csv", index=False)
            print(f"\n✅ Saved {len(df)} unique papers to research_catalog.csv")
        else:
            print("\n❌ No results found.")

    def run(self):
        try:
            print("🚀 Starting Mission...", flush=True)
            self.search_via_iterative_loop()
            
            # Fallback logic could go here if OpenAlex yields 0 results
            if len(self.results) == 0:
                print("⚠️ OpenAlex yielded 0 results. Trying Standard Text Search...")
                self.search_openalex_text_fallback()

        except KeyboardInterrupt: print("\nUser Interrupted.")
        finally: self.save_results()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--keywords")
    parser.add_argument("--author")
    parser.add_argument("--publication")
    parser.add_argument("--date_start")
    parser.add_argument("--date_end")
    parser.add_argument("--count", default=10, type=int)
    parser.add_argument("--sites")
    parser.add_argument("--keyword_logic", default="any")
    parser.add_argument("--no_llm", action="store_true", help="Disable all LLM/AI features to save quota")
    args = parser.parse_args()
    
    crawler = ResearchCrawler(args.topic, args.keywords, args.author, args.publication, 
                              args.date_start, args.date_end, args.count, args.sites, args.keyword_logic, args.no_llm)
    crawler.run()