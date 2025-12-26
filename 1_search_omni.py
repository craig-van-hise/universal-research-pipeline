import argparse
import time
import pandas as pd
import requests
import arxiv
from semanticscholar import SemanticScholar
from scholarly import scholarly
from habanero import Crossref
from unpywall import Unpywall
from sickle import Sickle
from bs4 import BeautifulSoup
from tqdm import tqdm
import os
import re
from urllib.parse import urlparse
import datetime
from dotenv import load_dotenv
import sys
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

# --- Configuration & Constants ---
CORE_API_KEY = os.getenv("CORE_API_KEY")
os.environ["UNPAYWALL_EMAIL"] = os.getenv("UNPAYWALL_EMAIL", "")

if not os.getenv("UNPAYWALL_EMAIL"):
    print("Warning: UNPAYWALL_EMAIL not found in .env. Unpaywall functionality will be limited.")

COLUMNS = [
    'Title', 'Authors', 'Original_Filename', 'Publication_Date', 'Category', 
    'Description', 'Is_Paywalled', 'Is_Downloaded', 'Source_URL', 'DOI'
]

# Robust Request Session
def get_session():
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

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

class ResearchCrawler:
    def __init__(self, topic, keywords, author, publication, date_start, date_end, count, sites, keyword_logic='any'):
        if os.path.exists("research_catalog.csv"):
            try:
                os.remove("research_catalog.csv")
            except OSError:
                pass

        self.raw_topic = topic
        raw_keywords = [k.strip() for k in keywords.split(',')] if keywords else []
        
        self.keywords_list = list(raw_keywords)
        for k in raw_keywords:
            if "personal sound zone" in k.lower():
                if "sound zone" not in [x.lower() for x in self.keywords_list]:
                    self.keywords_list.append("Sound Zone")
            if "psz" in k.lower():
                pass 

        self.author = author
        self.publication = publication
        
        print(f"DEBUG: Keywords: {self.keywords_list}")
        
        self.date_start = date_start
        self.date_end = date_end
        self.year_start = int(date_start[:4]) if date_start else 2000
        self.year_end = int(date_end[:4]) if date_end else 2030
        
        self.final_target_count = int(count)
        self.target_count = int(self.final_target_count * 1.2) + 5
        
        self.sites = sites if sites else ['all']
        self.results = []
        
        self.offsets = {
            'crossref': 0,
            'semantic': 0,
            'arxiv': 0,
            'openalex': 0
        }
        
        # Use session for stability
        self.session = get_session()
        
        sem_key = os.getenv("SEMANTIC_SCHOLAR_KEY")
        # Patch Semantic Scholar client if possible, or rely on our direct requests
        self.sch = SemanticScholar(api_key=sem_key) if sem_key else SemanticScholar()
        self.crossref = Crossref()
        self.keyword_logic = keyword_logic if keyword_logic else 'any'

    def _normalize_date(self, date_str):
        if not date_str:
            return f"{self.year_start}/01/01"
        try:
            if re.match(r'^\d{4}$', str(date_str)):
                return f"{date_str}/01/01"
            if re.match(r'^\d{4}-\d{2}-\d{2}$', str(date_str)):
                return str(date_str).replace('-', '/')
            return f"{self.year_start}/01/01"
        except:
             return f"{self.year_start}/01/01"

    def _is_date_in_range(self, date_str):
        try:
            norm_date = self._normalize_date(date_str)
            d = datetime.datetime.strptime(norm_date, "%Y/%m/%d").date()
            
            start = datetime.datetime.strptime(self.date_start, "%Y-%m-%d").date() if self.date_start else None
            end = datetime.datetime.strptime(self.date_end, "%Y-%m-%d").date() if self.date_end else None
            
            if start and d < start:
                return False
            if end and d > end:
                return False
            return True
        except:
            return True

    def _parse_filename(self, url):
        if not url:
            return 'Pending_Header_Check'
        path = urlparse(url).path
        filename = os.path.basename(path)
        if filename and (filename.lower().endswith('.pdf') or 'pdf' in url.lower()):
            if not filename.lower().endswith('.pdf'):
                return filename + ".pdf"
            return filename
        return 'Pending_Header_Check'

    def _contains_keywords(self, text):
        if not self.keywords_list:
            return True
        if not text:
            return False
        text_lower = text.lower()
        
        # ANY Logic: Return True if ANY keyword phrase matches
        if self.keyword_logic == 'any':
            for k in self.keywords_list:
                k_lower = k.lower()
                if k_lower in text_lower:
                    return True
                words = k_lower.split()
                if len(words) > 1 and all(w in text_lower for w in words):
                    return True
            return False
            
        # ALL Logic: Return True ONLY if ALL keyword phrases match
        elif self.keyword_logic == 'all':
            for k in self.keywords_list:
                k_lower = k.lower()
                match = False
                if k_lower in text_lower:
                    match = True
                else:
                    words = k_lower.split()
                    if len(words) > 1 and all(w in text_lower for w in words):
                        match = True
                
                if not match:
                    return False
            return True
            
        return False

    def _pre_filter(self, title, date, description):
        """Cheap CPU-bound checks before network calls"""
        full_text = f"{title} {description}"
        status, reason = self._is_date_in_range(date) if hasattr(self, '_is_date_in_range_tuple') else (self._is_date_in_range(date), "Date out of range")
        
        # Compat with existing _is_date_in_range returning bool
        if isinstance(status, bool) and not status:
             return False, "Date out of range"
        
        # Disabled strict local keyword check because APIs (Crossref/S2) search full text/metadata 
        # that we might not have locally (e.g. missing abstracts), causing false negatives.
        # if not self._contains_keywords(full_text):
        #    return False, "Keywords missing"
        
        norm_title = re.sub(r'[^a-z0-9]', '', str(title).lower())
        for existing in self.results:
            existing_norm = re.sub(r'[^a-z0-9]', '', str(existing['Title']).lower())
            if existing_norm == norm_title:
                return False, "Duplicate found"
        
        return True, "Passed"

    def _verify_candidate(self, candidate):
        """Worker function for parallel execution"""
        is_accessible, best_url = self._check_accessibility(candidate['url'], candidate['doi'])
        if is_accessible:
            candidate['final_url'] = best_url
            return candidate
        return None

    def _process_batch(self, candidates):
        """Process a batch of candidates in parallel"""
        print(f"DEBUG: Processing batch of {len(candidates)} candidates...", flush=True)
        
        # 1. CPU Filter
        valid_candidates = []
        for c in candidates:
            # Basic validation
            if not c.get('title'): continue
            
            passed, reason = self._pre_filter(c['title'], c['date'], c['description'])
            if passed:
                valid_candidates.append(c)
            else:
                # Optional: Verbose logging for rejections?
                pass

        if not valid_candidates:
            print("DEBUG: No candidates passed pre-filter.", flush=True)
            return

        print(f"DEBUG: {len(valid_candidates)} candidates passed pre-filter. Checking accessibility concurrently...", flush=True)

        # 2. Parallel I/O Check
        added_count = 0
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_cand = {executor.submit(self._verify_candidate, c): c for c in valid_candidates}
            
            for future in as_completed(future_to_cand):
                try:
                    result = future.result()
                    if result:
                        self._add_final_result(result)
                        added_count += 1
                except Exception as e:
                    print(f"Error in worker: {e}", flush=True)
        
        print(f"DEBUG: Batch complete. Added {added_count} papers.", flush=True)

    def _add_final_result(self, c):
        entry = {
            'Title': c['title'].strip() if c['title'] else "Unknown Title",
            'Authors': c['authors'] if c['authors'] else "Unknown Authors",
            'Original_Filename': self._parse_filename(c['final_url']),
            'Publication_Date': self._normalize_date(c['date']),
            'Category': 'Unsorted',
            'Description': c['description'][:2000] + "..." if c['description'] and len(c['description']) > 2000 else c['description'],
            'Is_Paywalled': False,
            'Is_Downloaded': False,
            'Source_URL': c['final_url'],
            'DOI': c['doi'],
            '_Source': c['source_name']
        }
        self.results.append(entry)
        print(f"[Accepted] {entry['Title'][:60]}...", flush=True)

    def _check_accessibility(self, url, doi):
        # Create a fresh, fast-fail session for validation checks
        # We do NOT want retries here; if it hangs, we skip it.
        check_session = requests.Session()
        check_adapter = HTTPAdapter(max_retries=0) # NO retries
        check_session.mount('http://', check_adapter)
        check_session.mount('https://', check_adapter)

        def is_valid_pdf_content(target_url):
            try:
                # stream=True to avoid downloading huge files if not PDF
                # Use a specific user agent to avoid generic bot blocks
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Range': 'bytes=0-1023' # Try to request just the header
                }
                # Fast timeout (2.5s), NO retries allowed by adapter
                r = check_session.get(target_url, headers=headers, stream=True, timeout=2.5, allow_redirects=True)
                
                # Check 1: Status Code
                if r.status_code not in [200, 206]:
                    return False
                
                # Check 2: Content-Type (weak check, but good early filter)
                ct = r.headers.get('Content-Type', '').lower()
                if 'text/html' in ct: 
                    return False
                
                # Check 3: Magic Bytes (Strongest Check)
                # Read start of content
                chunk = next(r.iter_content(chunk_size=1024), b'')
                r.close() # Close connection explicitly
                
                if b'%PDF' in chunk:
                    return True
                
                return False
            except Exception:
                return False
            finally:
                check_session.close()

        if url:
            if is_valid_pdf_content(url):
                return True, url

        if doi:
            try:
                # Unpaywall is fast/reliable, can keep using main session
                res = Unpywall.doi(doi)
                if res and res.best_oa_location and res.best_oa_location.url:
                    best_url = res.best_oa_location.url
                    # But validate the Result URL with the fast checker
                    if is_valid_pdf_content(best_url):
                        return True, best_url
            except:
                pass
        
        return False, url

    def search_openalex(self):
        base_url = "https://api.openalex.org/works"
        
        # Build filter string
        filters = ["is_oa:true", "has_doi:true"]
        if self.date_start:
             filters.append(f"publication_year:>{self.year_start-1}")
        if self.date_end:
             filters.append(f"publication_year:<{self.year_end+1}")
        
        filter_str = ",".join(filters)
        current_page = 1
        per_page = 200 # Max allowed
        
        # Construct precision query: "Topic" AND ("Keyword1" OR "Keyword2")
        topic_phrase = f'"{self.raw_topic}"'
        search_query = topic_phrase
        
        if self.keywords_list:
            # Quote each keyword phrase to ensure exact match (e.g. "crosstalk cancellation")
            quoted_keywords = [f'"{k}"' for k in self.keywords_list]
            
            if self.keyword_logic == 'all':
                # Topic AND "Key1" AND "Key2"...
                joined_keywords = " AND ".join(quoted_keywords)
                search_query = f'{topic_phrase} AND {joined_keywords}'
            else:
                # Default ANY: Topic AND ("Key1" OR "Key2"...)
                joined_keywords = " OR ".join(quoted_keywords)
                search_query = f'{topic_phrase} AND ({joined_keywords})'

        print(f"📚 Querying OpenAlex for: '{search_query}'...", flush=True)

        # Loop until GLOBAL result count hits target, so we truly fill the bucket
        while len(self.results) < self.target_count:
            params = {
                "search": search_query,
                "filter": filter_str,
                "per-page": per_page,
                "page": current_page,
                "select": "title,id,publication_year,open_access,authorships,abstract_inverted_index,doi"
            }

            try:
                resp = requests.get(base_url, params=params, timeout=10)
                if resp.status_code != 200: 
                    print(f"OpenAlex Error: {resp.status_code}")
                    break
                    
                results = resp.json().get('results', [])
                if not results: 
                    print("OpenAlex: No more results.")
                    break
                    
                batch_candidates = []
                for item in results:
                    pdf_url = item.get('open_access', {}).get('oa_url')
                    if not pdf_url: continue # Should be caught by is_oa:true but safe check

                    # Reconstruct abstract
                    abstract_text = reconstruct_abstract(item.get('abstract_inverted_index'))

                    # Get author
                    authors_list = item.get('authorships', [])
                    first_author = authors_list[0]['author']['display_name'] if authors_list else "Unknown"
                    all_authors = ", ".join([a.get("author", {}).get("display_name", "") for a in authors_list])

                    # Trust OpenAlex relevance since we included keywords in the query
                    # Local keyword check removed to prevent false negatives (keywords in fulltext but not abstract)

                    # Normalize keys for _process_batch
                    batch_candidates.append({
                        'title': item['title'],
                        'authors': all_authors, 
                        'date': str(item.get('publication_year', '')),
                        'description': abstract_text,
                        'doi': item.get('doi', '').replace("https://doi.org/", ""),
                        'url': pdf_url, 
                        'source_name': 'OpenAlex'
                    })
                
                # Use the robust parallel processor which includes VALIDATION
                self._process_batch(batch_candidates)

                current_page += 1
                if current_page > 50: # Safety break (check up to 10k papers)
                    print("OpenAlex: Reached safety page limit (50). Stopping.")
                    break
                
            except Exception as e:
                print(f"Error searching OpenAlex: {e}", flush=True)
                break

    def search_arxiv(self):
        if self.offsets['arxiv'] > 0:
            return 

        print(f"Searching ArXiv...", flush=True)
        try:
            if self.keywords_list:
                kw_parts = []
                for k in self.keywords_list:
                    words = k.split()
                    if len(words) > 1:
                        sub_query = " AND ".join([f'all:"{w}"' for w in words])
                        kw_parts.append(f"({sub_query})")
                    else:
                        kw_parts.append(f'all:"{k}"')
                
                kw_group = " OR ".join(kw_parts)
                if self.keyword_logic == 'all':
                    kw_group = " AND ".join(kw_parts)
                
                final_query = f'all:"{self.raw_topic}" AND ({kw_group})'
            else:
                final_query = f'all:"{self.raw_topic}"'

            if self.author:
                final_query += f' AND au:"{self.author}"'
            
            client = arxiv.Client()
            search = arxiv.Search(
                query=final_query,
                max_results=self.target_count * 2, 
                sort_by=arxiv.SortCriterion.SubmittedDate
            )

            candidates = []
            for result in tqdm(client.results(search), desc="ArXiv"):
                pdf_link = result.pdf_url
                if pdf_link and 'arxiv.org/abs/' in pdf_link:
                    pdf_link = pdf_link.replace('abs', 'pdf')
                
                authors = ", ".join([a.name for a in result.authors])
                pub_date = str(result.published.date())
                
                candidates.append({
                    'title': result.title,
                    'authors': authors,
                    'url': pdf_link,
                    'date': pub_date,
                    'description': result.summary,
                    'doi': result.doi,
                    'source_name': 'ArXiv'
                })
            
            self._process_batch(candidates)
            self.offsets['arxiv'] = 1 
                
        except Exception as e:
            print(f"Error searching ArXiv: {e}")

    def search_semantic_scholar(self):
        print(f"Searching Semantic Scholar (Offset: {self.offsets['semantic']})...", flush=True)
        try:
            if self.keywords_list:
                if self.keyword_logic == 'all':
                    combined_k = " ".join(self.keywords_list)
                    search_terms = [f"{self.raw_topic} {combined_k}"]
                else:
                    search_terms = [f"{self.raw_topic} {k}" for k in self.keywords_list]
            else:
                search_terms = [self.raw_topic]
            limit_per_call = 20
            
            for term in search_terms:
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                
                params = {
                    "query": term,
                    "offset": self.offsets['semantic'],
                    "limit": limit_per_call, 
                    "fields": "title,authors,abstract,publicationDate,url,openAccessPdf,externalIds,venue",
                    "openAccessPdf": "true"
                }
                
                headers = {}
                sem_key = os.getenv("SEMANTIC_SCHOLAR_KEY")
                if sem_key: headers["x-api-key"] = sem_key

                try:
                    r = self.session.get(url, params=params, headers=headers, timeout=10)
                    
                    if r.status_code == 429:
                        time.sleep(5)
                        continue
                    
                    data = r.json()
                    papers = data.get("data", [])
                    if papers:
                        candidates = []
                        for item in papers:
                            item_authors = item.get("authors", [])
                            author_names = ", ".join([a.get("name","") for a in item_authors])
                            
                            if self.author and self.author.lower() not in author_names.lower():
                                continue

                            pdf_url = item.get("url")
                            oa_pdf = item.get("openAccessPdf")
                            if oa_pdf and oa_pdf.get("url"):
                                pdf_url = oa_pdf.get("url")

                            candidates.append({
                                'title': item.get("title"),
                                'authors': author_names,
                                'url': pdf_url,
                                'date': str(item.get("publicationDate")),
                                'description': item.get("abstract"),
                                'doi': (item.get("externalIds") or {}).get("DOI"),
                                'source_name': 'Semantic Scholar'
                            })
                        
                        self._process_batch(candidates)
                except Exception:
                    pass
            
            self.offsets['semantic'] += limit_per_call

        except Exception as e:
            print(f"Error searching Semantic Scholar: {e}")

    def search_crossref(self):
        # DEPRECATED IN FAVOR OF OPENALEX
        # print(f"Searching Crossref (Offset: {self.offsets['crossref']})...")
        return 

    def save_results(self):
        df = pd.DataFrame(self.results)
        if df.empty:
            print("No results found or processed.")
            df.to_csv("research_catalog.csv", index=False)
            return

        df['norm_title'] = df['Title'].apply(lambda x: re.sub(r'[^a-z0-9]', '', str(x).lower()) if x else '')
        df = df.drop_duplicates(subset=['norm_title'], keep='first')
        
        if len(df) > self.final_target_count:
            print(f"Trimming results from {len(df)} to requested {self.final_target_count}...")
            df = df.head(self.final_target_count)
            
        df = df.drop(columns=['norm_title'], errors='ignore')

        df.to_csv("research_catalog.csv", index=False)
        print(f"Saved {len(df)} papers to research_catalog.csv")

    def run(self):
        try:
            # OpenAlex First (Highest Quality/Speed)
            self.search_openalex()
            
            if len(self.results) >= self.final_target_count:
                print("Target met with OpenAlex. Skipping other sources.")
                return

            # Fallback to others
            buffer_target = int(self.final_target_count * 1.2) + 5
            rounds = 0
            max_rounds = 10
            
            while len(self.results) < buffer_target and rounds < max_rounds:
                rounds += 1
                current_count = len(self.results)
                print(f"\n--- Search Round {rounds} (Collected: {current_count}/{buffer_target} for target {self.final_target_count}) ---")
                
                # self.search_crossref() # Deprecated
                self.search_arxiv()
                self.search_semantic_scholar()
                
                new_count = len(self.results)
                if new_count == current_count:
                    print(f">> Round {rounds}: No new papers added. Digging deeper...")
            
        except KeyboardInterrupt:
            print("\nUser Interrupted.")
        except Exception:
            pass
        finally:
            self.save_results()

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
    parser.add_argument("--validate", action="store_true", help="Run self-diagnostic smoke test")
    args = parser.parse_args()
    
    if args.validate:
        print("--- SELF-DIAGNOSTIC REPORT ---")
        start_time = time.time()
        
        # Test Search: Generative AI, Target 5
        crawler = ResearchCrawler(
            topic="Generative AI",
            keywords="",
            author="",
            publication="",
            date_start="",
            date_end="",
            count=5,
            sites=['openalex'],
            keyword_logic="any"
        )
        
        # Override run to just use openalex for test
        crawler.search_openalex()
        
        duration = time.time() - start_time
        print(f"✅ Search Complete: {duration:.2f}s")
        
        papers_found = len(crawler.results)
        print(f"✅ Papers Found: {papers_found}/5")
        
        link_health = 0
        valid_abstracts = 0
        
        with requests.Session() as s:
            for p in crawler.results:
                try:
                    r = s.head(p['Source_URL'], timeout=5, allow_redirects=True)
                    if r.status_code == 200:
                        link_health += 1
                except:
                    pass
                
                if p['Description'] and len(p['Description']) > 50:
                    valid_abstracts += 1
                    
        print(f"✅ Link Health: {link_health}/{papers_found} (200 OK)")
        print(f"✅ Abstract Reconstruction: {valid_abstracts}/{papers_found} Valid")
        print("------------------------------")
        sys.exit(0)

    sites_list = [s.strip().lower() for s in args.sites.split(',')] if args.sites else ['all']
    
    crawler = ResearchCrawler(
        topic=args.topic,
        keywords=args.keywords,
        author=args.author,
        publication=args.publication,
        date_start=args.date_start,
        date_end=args.date_end,
        count=args.count,
        sites=sites_list,
        keyword_logic=args.keyword_logic
    )
    crawler.run()
