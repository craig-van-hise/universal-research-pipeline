import pandas as pd
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import os
import re
import csv
import json
import shutil
from urllib.parse import urlparse, unquote
from tqdm import tqdm
import time
import random
from bs4 import BeautifulSoup
from googlesearch import search
from ddgs import DDGS
from unpywall import Unpywall
from unpywall.utils import UnpywallCredentials
UnpywallCredentials('vv@scholar-stack.com') # Using user email logic or placeholder

def sanitize_filename(name):
    """Sanitizes filenames to be OS-safe."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def generate_filename(paper, format_option="Title"):
    """
    Generates a filename based on the user's selected format.
    Options: 'Title', 'Author - Year - Title', 'Year - Journal - Title'
    """
    title = paper.get('Title', 'Untitled')
    # Basic clean first
    title = sanitize_filename(title)
    
    if format_option == "Title":
        base = title
    elif format_option == "Author - Year - Title":
        # Extract first author
        authors_raw = paper.get('Authors', [])
        # If it's a string (from CSV), split it
        if isinstance(authors_raw, str):
            authors_list = authors_raw.split(';')
        else:
            authors_list = authors_raw
            
        first_auth = "Unknown"
        if authors_list and len(authors_list) > 0:
            first_auth = authors_list[0].split(',')[0].strip() # Just surname if possible
            first_auth = sanitize_filename(first_auth)
            
        year = str(paper.get('Year', '0000'))
        base = f"{first_auth} - {year} - {title}"
        
    elif format_option == "Year - Journal - Title":
        year = str(paper.get('Year', '0000'))
        journal = paper.get('Journal', 'Journal')
        if not journal or str(journal) == 'nan': journal = "Journal"
        journal = sanitize_filename(journal)
        base = f"{year} - {journal} - {title}"
    else:
        base = title
        
    # Truncate to avoid OS errors (255 max, keeping extension room)
    if len(base) > 240:
        base = base[:240]
        
    return base + ".pdf"

def get_filename_from_cd(cd):
    """Get filename from content-disposition header."""
    if not cd:
        return None
    fname = re.findall(r'filename=["\']?([^"\';]+)["\']?', cd)
    if len(fname) == 0:
        return None
    return fname[0].strip()

def create_markdown_catalog(papers, topic, output_path, search_params=None):
    """Generates a human-readable Markdown catalog."""
    with open(output_path, "w", encoding="utf-8") as f:
        downloaded_count = sum(1 for p in papers if p.get('is_downloaded'))
        f.write(f"# Library Catalog: {topic}\n\n")
        
        if search_params:
            f.write("## Search Settings\n")
            for k, v in search_params.items():
                if v: f.write(f"- **{k}:** {v}\n")
            f.write("\n")
            
        f.write(f"**Total Papers Listed:** {len(papers)}  \n")
        f.write(f"**Total Papers Downloaded:** {downloaded_count}  \n")
        f.write(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        # Sort keys for grouping? Assuming papers list is already sorted or we group here.
        # But 'papers' is a list of dicts. We need to group by Category.
        # Simple approach: Convert back to DF for easy grouping or use itertools.groupby
        # Let's stick to simple iteration if already sorted, or just re-sort.
        papers_sorted = sorted(papers, key=lambda x: (x.get('category', 'Uncategorized'), x.get('title', '')))
        
        current_cat = None
        for paper in papers_sorted:
            cat = paper.get('category', 'Uncategorized')
            if cat != current_cat:
                f.write(f"## {cat}\n\n")
                f.write("| Title | First Author | Year | Journal | Citations | Link |\n")
                f.write("|---|---|---|---|---|---|\n")
                current_cat = cat
            
            title = paper.get('title', 'Unknown Title').replace('|', '-') # Escape pipes
            
            authors_list = paper.get('authors', [])
            if not authors_list:
                first_author = "Unknown"
            else:
                first_author = authors_list[0]
                if len(authors_list) > 1:
                    first_author += " et al."
            
            year = str(paper.get('year', ''))
            journal = str(paper.get('journal', ''))
            citations = str(paper.get('citation_count', ''))
            if citations == 'None': citations = ''
            
            url = paper.get('url', '')
            link = f"[Source]({url})" if url else "N/A"
            
            f.write(f"| {title} | {first_author} | {year} | {journal} | {citations} | {link} |\n")
        f.write("\n")

def create_csv_catalog(papers, output_path):
    """Generates a strictly quoted CSV catalog."""
    headers = ['Title', 'Authors', 'Year', 'Journal', 'DOI', 'Citation_Count', 'URL', 'PDF_Link', 'Filename', 'Abstract']
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        
        for p in papers:
            authors_str = "; ".join(p.get('authors', []))
            writer.writerow({
                'Title': p.get('title', ''),
                'Authors': authors_str,
                'Year': p.get('year', ''),
                'Journal': p.get('journal', ''),
                'DOI': p.get('doi', ''),
                'Citation_Count': p.get('citation_count', 0),
                'URL': p.get('url', ''),
                'PDF_Link': p.get('pdf_url', ''),
                'Filename': p.get('filename', ''),
                'Abstract': p.get('abstract', '')
            })

def create_ris_catalog(papers, output_path):
    """Generates an RIS file for reference managers."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for p in papers:
            f.write("TY  - JOUR\n")
            f.write(f"TI  - {p.get('title', '')}\n")
            
            for auth in p.get('authors', []):
                f.write(f"AU  - {auth}\n")
                
            f.write(f"PY  - {p.get('year', '')}\n")
            f.write(f"JO  - {p.get('journal', '')}\n")
            
            if p.get('doi'): f.write(f"DO  - {p.get('doi')}\n")
            if p.get('url'): f.write(f"UR  - {p.get('url')}\n")
            if p.get('pdf_url'): f.write(f"L1  - {p.get('pdf_url')}\n")
            if p.get('abstract'): f.write(f"AB  - {p.get('abstract')}\n")
            
            f.write("ER  - \n\n")

def generate_citation_key(paper, existing_keys):
    """Generates a unique BibTeX citation key: [FirstAuthor][Year][FirstTitleWord]"""
    # 1. First Author
    authors = paper.get('authors', [])
    if authors:
        # Assuming "First Last" or "Last, First". Heuristic: split by space, take last part of first element?
        # Standardized format usually "First Last" in list?
        # Let's try to be smart. Remove weird chars.
        first_auth_full = authors[0]
        # remove content in parens if any
        first_auth_full = re.sub(r'\(.*?\)', '', first_auth_full).strip()
        # Take last word as surname (rough heuristic)
        surname = first_auth_full.split()[-1] if first_auth_full else "Unknown"
        surname = "".join(filter(str.isalnum, surname))
    else:
        surname = "Unknown"
        
    # 2. Year
    year = str(paper.get('year', '0000'))
    if not year.isdigit(): year = "0000"
    
    # 3. First Word of Title
    title = paper.get('title', 'Untitled')
    # filtered title
    title_words = [w for w in re.split(r'[^a-zA-Z0-9]', title) if w]
    first_word = title_words[0] if title_words else "Doc"
    
    base_key = f"{surname}{year}{first_word}"
    
    key = base_key
    suffix = 97 # 'a'
    while key in existing_keys:
        key = f"{base_key}_{chr(suffix)}"
        suffix += 1
        if suffix > 122: # z
             key = f"{base_key}_{suffix}" # Fallback to numbers if we run out of letters
    
    return key

def create_bibtex_catalog(papers, output_path):
    """Generates a BibTeX file for LaTeX support."""
    existing_keys = set()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for p in papers:
            # Generate Unique Key
            cite_key = generate_citation_key(p, existing_keys)
            existing_keys.add(cite_key)
            
            # Format Authors (BibTeX uses "Last, First and Last, First" or "First Last and First Last")
            # We have "First Last" strings. Join with " and ".
            authors_bib = " and ".join(p.get('authors', []))
            
            f.write(f"@article{{{cite_key},\n")
            f.write(f"  title = {{{p.get('title', '')}}},\n")
            f.write(f"  author = {{{authors_bib}}},\n")
            f.write(f"  year = {{{p.get('year', '')}}},\n")
            f.write(f"  journal = {{{p.get('journal', '')}}},\n")
            if p.get('doi'): f.write(f"  doi = {{{p.get('doi')}}},\n")
            if p.get('url'): f.write(f"  url = {{{p.get('url')}}},\n")
            if p.get('abstract'): 
                 # Basic escaping for abstract
                 abs_text = p.get('abstract', '').replace('%', '\\%').replace('{', '\\{').replace('}', '\\}')
                 f.write(f"  abstract = {{{abs_text}}}\n")
            f.write("}\n\n")

def sanitize_folder_name(name):
    clean = "".join([c if c.isalnum() or c in (' ', '_', '-') else '' for c in name])
    return clean.strip().replace(' ', '_')

# ... (skipping unchanged helpers) ...

def download_library(limit=None, sort_by="Most Relevant", **kwargs):
    print("=== Phase 4: The Physical Librarian (V9: Robust) ===")
    
    csv_path = "research_catalog_categorized.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return
    
    if 'Is_Downloaded' not in df.columns:
        df['Is_Downloaded'] = False
        
    if 'Directory_Path' not in df.columns:
        print("Error: 'Directory_Path' column missing.")
        return

    if 'Topic' not in df.columns or df['Topic'].isnull().all():
        print("Error: 'Topic' column missing.")
        return
        
    current_topic = df['Topic'].iloc[0]
    print(f"Processing Topic: {current_topic}")
    
    # --- NEW: Prioritization & Trimming Logic ---
    print(f"Applying Filter: Sort by '{sort_by}', Limit to {limit} papers.")
    
    # Ensure Publication_Date is comparable
    if 'Publication_Date' in df.columns:
        df['Publication_Date'] = pd.to_datetime(df['Publication_Date'], errors='coerce')
    
    # 1. Sort
    if sort_by == "Date: Newest":
        df = df.sort_values(by='Publication_Date', ascending=False)
    elif sort_by == "Date: Oldest":
        df = df.sort_values(by='Publication_Date', ascending=True)
    elif sort_by == "Citations: Most":
        print("Sorting papers by Citations (Most First)...")
        if 'Citation_Count' in df.columns:
            df['Citation_Count'] = pd.to_numeric(df['Citation_Count'], errors='coerce').fillna(0)
            df = df.sort_values(by='Citation_Count', ascending=False)
    elif sort_by == "Citations: Least":
        print("Sorting papers by Citations (Least First)...")
        if 'Citation_Count' in df.columns:
            df['Citation_Count'] = pd.to_numeric(df['Citation_Count'], errors='coerce').fillna(0)
            df = df.sort_values(by='Citation_Count', ascending=True)
    # else: "Most Relevant" -> assumes input order is relevance (from API)

    # 2. Trim
    if limit:
        original_count = len(df)
        df = df.head(limit)
        print(f"Trimmed candidate list from {original_count} to {len(df)} papers.")
    
    success_count = 0
    fail_count = 0
    
    # --- NEW: Parallel Download Logic ---
    def process_paper_wrapper(args):
        index, row = args
        
        target_dir = row['Directory_Path'] if pd.notna(row['Directory_Path']) else f"./Library/{sanitize_folder_name(current_topic)}"
        os.makedirs(target_dir, exist_ok=True)
        
        success, final_url, fname, paywalled = False, None, None, False
        
        if row['Is_Downloaded']:
             return (index, True, row['Source_URL'], row['Original_Filename'], False)

        try:
            # 1. Primary Download
            url = row['Source_URL']
            doi = row['DOI']
            title = row['Title']
            
            # Use original filename if possible, else sanitizer
            filename = row['Original_Filename'] 
            if not filename or filename == 'Pending_Header_Check':
                filename = sanitize_filename(title[:50]) + ".pdf"
            
            path = os.path.join(target_dir, filename)
            
            success = download_file(url, path)
            
            # ... (Rest of download logic is handled inside download_file or wrapper, minimizing code duplicaton here)
            # Actually, to avoid re-writing 200 lines, I assume download_file handles logic.
            # But wait, original code had a huge loop. I should keep the helper I wrote in previous turn? 
            # Ah, I don't see the helper in the viewed file. Did I lose it?
            # No, I am REPLACING the whole function. I must re-implement the loop logic carefully.
            # OR I use the helper if it exists.
            # Let's check line 448 in existing file... ah, I only viewed 450+.
            
            # Wait, the replace block covers up to line 603 (end of file).
            # I must ensure I don't lose the parallel logic I added earlier.
            
            # Let me just re-implement the ThreadPool logic cleanly here, assuming helpers exist.
            # Actually, I should use the `download_library` I see in lines 395-450, and extends it.
            
            # The parallel logic was added in a previous turn (Step 567 in logs).
            # I need to make sure I don't overwrite it with a bad copy.
            
            pass 
        except: pass
        return (index, False, None, None, True)

    # RE-READING: I see I am replacing `create_markdown_catalog` and `download_library`.
    # I need to make sure I include the PARALLEL LOGIC I added in the previous session.
    # Since I cannot see the full `process_paper_wrapper` from my `view_file` (it started at 350 and I see the top of `download_library` at 395), I must be careful.
    
    # ACTUALLY, I will ONLY replace `create_markdown_catalog` and the END of `download_library` where the catalog is generated.
    # I will split this into TWO edits to be safe.
    
    # Edit 1: update `create_markdown_catalog` (lines 33-65).
    # Edit 2: update the END of `download_library` (lines 578-583) to pass params.
    
    return # Dummy return to stop this tool call from running with this massive block.

# ABORTING MASSIVE REPLACEMENT. Splitting into smaller, safer edits.

def sanitize_folder_name(name):
    clean = "".join([c if c.isalnum() or c in (' ', '_', '-') else '' for c in name])
    return clean.strip().replace(' ', '_')

def get_pdf_from_unpywall(doi):
    """Fallback: Try to find a direct PDF link via Unpywall."""
    if not doi or str(doi) == 'nan': return None
    try:
        # 1. Unpywall requires a LIST of DOIs
        res = Unpywall.doi([doi])
        if res is not None and not res.empty:
             # Try PDF URL first
             best_url = res.iloc[0].get('best_oa_location.url_for_pdf')
             if best_url: return best_url
             
             # Fallback to generic URL (sometimes it's a direct download link disguised)
             fallback_url = res.iloc[0].get('best_oa_location.url')
             if fallback_url: return fallback_url
             
             # Fallback to FIRST oa location if 'best' is weird
             first_url = res.iloc[0].get('first_oa_location.url')
             if first_url: return first_url
    except Exception as e: 
        pass
    return None

def get_pdf_from_meta_tags(url):
    """Scrapes landing page for <meta name='citation_pdf_url'> OR visible PDF links."""
    if not url or url.lower().endswith('.pdf'): return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        r = requests.get(url, headers=headers, timeout=5)
        
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'html.parser')
            
            # 1. Standard Google Scholar Meta Tag
            meta_pdf = soup.find('meta', attrs={'name': 'citation_pdf_url'})
            if meta_pdf and meta_pdf.get('content'):
                candidate = meta_pdf['content']
                if 'localhost' in candidate and 'tu-berlin' in url:
                    candidate = candidate.replace('http://localhost:4000', 'https://depositonce.tu-berlin.de')
                print(f"   [Meta Scraper] Found PDF (Meta): {candidate}")
                return candidate
            
            # 2. Body Scanning (The "Click the Button" Strategy)
            # Find all <a> tags with href containing '.pdf'
            from urllib.parse import urljoin
            
            # Strategy A: Strict .pdf extension
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                text = link.text.lower()
                
                # Check for PDF extension
                if href.lower().endswith('.pdf') or 'type=pdf' in href.lower():
                    # Check for "Full Text", "Download", "View" to prioritize good links
                    # Or closest link if list is short? 
                    # Let's take the first one that looks like a paper download
                    full_url = urljoin(url, href)
                    print(f"   [Page Scraper] Found PDF link: {full_url}")
                    return full_url
            
            # Strategy B: Button text contains "PDF"
            for link in links:
                if 'pdf' in link.text.lower() or 'download' in link.text.lower():
                     full_url = urljoin(url, link['href'])
                     # A bit risky, but better than nothing
                     if 'javascript' not in full_url:
                        print(f"   [Page Scraper] Found PDF button: {full_url}")
                        return full_url
                        
    except Exception as e: 
        print(f"   [Meta Scraper] Error scraping {url}: {e}")
        pass
    return None

def attempt_secondary_search(title):
    """Fallback: Search Semantic Scholar for alternative PDF links or DOIs."""
    if not title or len(str(title)) < 10: return None
    
    print(f"   [Secondary Search] Hunting for '{title[:30]}...'")
    for attempt in range(2):
        try:
            # 1. Search Semantic Scholar
            params = {'query': title, 'limit': 1, 'fields': 'title,openAccessPdf,externalIds,url'}
            r = requests.get('https://api.semanticscholar.org/graph/v1/paper/search', params=params, timeout=5)
            
            if r.status_code == 200:
                data = r.json()
                if data.get('data'):
                    paper = data['data'][0]
                    # Fuzzy Title Check
                    match_ratio = len(set(title.lower().split()) & set(paper['title'].lower().split())) / len(title.split())
                    
                    if match_ratio > 0.6:
                        # Strategy A: OpenAccess PDF from S2
                        pdf_info = paper.get('openAccessPdf')
                        if pdf_info and pdf_info.get('url'):
                            cand_url = pdf_info['url']
                            # Fix ArXiv Abs links
                            if 'arxiv.org/abs' in cand_url:
                                cand_url = cand_url.replace('/abs/', '/pdf/') + ".pdf"
                            
                            # Skip known bad domains if they don't look like PDFs
                            if 'aes.org' in cand_url and not cand_url.endswith('.pdf'):
                                pass
                            else:
                                print(f"   [Secondary Search] Found URL: {cand_url}")
                                return cand_url
                        
                        # Strategy B: Found a new DOI? Try Unpywall again!
                        ids = paper.get('externalIds', {})
                        new_doi = ids.get('DOI')
                        if new_doi:
                            print(f"   [Secondary Search] Found DOI {new_doi}. Re-trying Unpywall...")
                            unp_url = get_pdf_from_unpywall(new_doi)
                            if unp_url: return unp_url

                        # Strategy C: ArXiv ID?
                        if ids.get('ArXiv'):
                            arxiv_id = ids.get('ArXiv')
                            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
                break # Success or no match
                            
            elif r.status_code == 429:
                 wait = (attempt + 1) * 5
                 print(f"   [Secondary Search] Rate Limit Hit. Waiting {wait}s...")
                 time.sleep(wait)
                 continue
                 
        except: pass
        
    # time.sleep(2) # Politeness delay removed for speed

    return None

def attempt_ddg_fallback(title):
    """Fallback: Use DuckDuckGo to find PDF candidates (Direct or via Landing Page)."""
    print(f"   [DDG Rescue] Hunting for '{title[:30]}...'")
    candidates = []
    seen_urls = set()
    
    try:
        with DDGS() as ddgs:
            # 1. Strict PDF Search
            query = f'"{title}" filetype:pdf'
            results = list(ddgs.text(query, max_results=3))
            
            for r in results:
                url = r.get('href', '')
                if url in seen_urls: continue
                
                if url.lower().endswith('.pdf'):
                    if 'researchgate.net' in url: continue
                    print(f"   [DDG Rescue] Found PDF Candidate: {url}")
                    candidates.append(url)
                    seen_urls.add(url)
            
            # 2. Relaxed Search & Scrape
            query = f'{title} pdf'
            results = list(ddgs.text(query, max_results=5))
            for r in results:
                url = r.get('href', '')
                if url in seen_urls: continue
                
                # A. Direct PDF
                if url.lower().endswith('.pdf'):
                    if 'researchgate.net' in url: continue
                    print(f"   [DDG Rescue] Found PDF Candidate (Ext): {url}")
                    candidates.append(url)
                    seen_urls.add(url)
                    continue
                
                # B. ArXiv Check
                if 'arxiv.org/abs' in url:
                    pdf_url = url.replace('/abs/', '/pdf/') + ".pdf"
                    print(f"   [DDG Rescue] Found ArXiv Candidate: {pdf_url}")
                    candidates.append(pdf_url)
                    seen_urls.add(pdf_url)
                    continue
                    
                # C. Landing Page Scrape (The "Human Click" Strategy)
                if 'books.google' in url or 'scholar.google' in url or 'researchgate.net' in url: continue
                
                # Only scrape if we don't have enough candidates yet
                if len(candidates) >= 3: break
                
                print(f"   [DDG Rescue] Checking candidate page: {url}")
                scraped_pdf = get_pdf_from_meta_tags(url)
                if scraped_pdf and scraped_pdf not in seen_urls:
                    print(f"   [DDG Rescue] Extracted PDF from page: {scraped_pdf}")
                    candidates.append(scraped_pdf)
                    seen_urls.add(scraped_pdf)

    except Exception as e:
        print(f"   [DDG Rescue] Error: {e}")
        
    return candidates  # Returns list

def attempt_google_fallback(title):
    """Last Resort: Mimic User's 'Google It' behavior."""
    print(f"   [Google Rescue] Hunting for '{title[:30]}...'")
    try:
        # Strict search first
        query = f'"{title}" filetype:pdf'
        results = search(query, num_results=3, advanced=True)
        for r in results:
            if r.url.endswith('.pdf'):
                print(f"   [Google Rescue] Found PDF: {r.url}")
                return r.url
        
        # Looser search: Check HEAD of top results
        query = f'{title} pdf'
        print(f"   [Google Rescue] Deep Scanning for: {query}")
        
        # 1. Fetch Candidates (up to 7)
        candidates = []
        try:
             results = search(query, num_results=7, advanced=True)
             for r in results:
                 candidates.append(r.url)
        except: pass
        
        for url in candidates:
            # A. Known Patterns
            if 'arxiv.org/abs' in url:
                pdf_url = url.replace('/abs/', '/pdf/') + ".pdf"
                print(f"   [Google Rescue] Found ArXiv: {pdf_url}")
                return pdf_url
            
            # B. Extension Check
            if url.lower().endswith('.pdf'):
                print(f"   [Google Rescue] Found PDF (Ext): {url}")
                return url
                
            # C. HEAD CHECK (The "Nuclear" Option)
            # Checks if a URL *serves* a PDF even if it doesn't look like one
            try:
                h_headers = {'User-Agent': random.choice([
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ])}
                # Quick HEAD request (3s timeout)
                h = requests.head(url, headers=h_headers, timeout=3, allow_redirects=True)
                
                # Check Content-Type
                ct = h.headers.get('Content-Type', '').lower()
                if 'application/pdf' in ct:
                    print(f"   [Google Rescue] Found PDF (HEAD): {url}")
                    return url
                    
                # Content-Disposition check
                cd = h.headers.get('Content-Disposition', '').lower()
                if 'pdf' in cd and 'attachment' in cd:
                     print(f"   [Google Rescue] Found PDF (Disp): {url}")
                     return url
                     
            except: pass
            
    except Exception as e:
        pass
    return None

def download_file(url, local_path):
    """Robust download with retries and header validation."""
    if not url: return False
    
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'
    ]
    
    # 1. Try Direct Method
    for attempt in range(2):
        try:
            ua = random.choice(user_agents)
            headers = {
                'User-Agent': ua,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://scholar.google.com/'
            }
            
            # Special Handling for MDPI (needs cookies sometimes, but headers usually work)
            if 'mdpi.com' in url:
                headers['Upgrade-Insecure-Requests'] = '1'
                headers['Sec-Fetch-Dest'] = 'document'
                headers['Sec-Fetch-Mode'] = 'navigate'
                headers['Sec-Fetch-Site'] = 'none'
                headers['Sec-Fetch-User'] = '?1'

            # SSL Verify=False for older academic repos (IOA, TU-Berlin sometimes have cert issues)
            # Timeout reduced to 10s to fail fast
            r = requests.get(url, headers=headers, stream=True, timeout=10, verify=False)
            
            if r.status_code == 403:
                time.sleep(2) # Backoff for 403
                continue
                
            if r.status_code == 200:
                # Content-Type Check (Permissive)
                ct = r.headers.get('Content-Type', '').lower()
                if 'text/html' in ct and len(r.content) < 50000:
                    # Likely a landing page, not a PDF
                    pass 
                else:
                    with open(local_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    # Validate Magic Bytes
                    if os.path.exists(local_path):
                        with open(local_path, 'rb') as f:
                            head = f.read(1024)
                        if b'%PDF' in head:
                            return True
                        else:
                            os.remove(local_path) # Corrupt
        except Exception: 
            pass
            
    return False

def download_library(limit=None, sort_by="Most Relevant", filename_format="Title", **kwargs):
    print("=== Phase 4: The Physical Librarian (V9: Robust) ===")
    
    csv_path = "research_catalog_categorized.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return
    
    if 'Is_Downloaded' not in df.columns:
        df['Is_Downloaded'] = False
        
    if 'Directory_Path' not in df.columns:
        print("Error: 'Directory_Path' column missing.")
        return

    if 'Topic' not in df.columns or df['Topic'].isnull().all():
        print("Error: 'Topic' column missing.")
        return
        
    current_topic = df['Topic'].iloc[0]
    print(f"Processing Topic: {current_topic}")
    
    # --- NEW: Prioritization & Trimming Logic ---
    print(f"Applying Filter: Sort by '{sort_by}', Limit to {limit} papers.")
    
    # Ensure Publication_Date is comparable
    if 'Publication_Date' in df.columns:
        df['Publication_Date'] = pd.to_datetime(df['Publication_Date'], errors='coerce')
    
    # 1. Sort
    if sort_by == "Date: Newest":
        df = df.sort_values(by='Publication_Date', ascending=False)
    elif sort_by == "Date: Oldest":
        df = df.sort_values(by='Publication_Date', ascending=True)
    elif sort_by == "Citations: Most":
        print("Sorting papers by Citations (Most First)...")
        if 'Citation_Count' in df.columns:
            df['Citation_Count'] = pd.to_numeric(df['Citation_Count'], errors='coerce').fillna(0)
            df = df.sort_values(by='Citation_Count', ascending=False)
    elif sort_by == "Citations: Least":
        print("Sorting papers by Citations (Least First)...")
        if 'Citation_Count' in df.columns:
            df['Citation_Count'] = pd.to_numeric(df['Citation_Count'], errors='coerce').fillna(0)
            df = df.sort_values(by='Citation_Count', ascending=True)
    # else: "Most Relevant" -> assumes input order is relevance (from API)

    # 2. Trim
    if limit:
        original_count = len(df)
        df = df.head(limit)
        print(f"Trimmed candidate list from {original_count} to {len(df)} papers.")
    
    success_count = 0
    fail_count = 0
    
    print(f"Found {len(df)} papers. Starting download process...")

    print(f"Found {len(df)} papers. Starting download process (Parallel Execution)...")

    # --- Helper Function for Threading ---
    def process_paper_wrapper(args):
        index, row = args
        title = row.get('Title', 'Unknown_Paper')
        dest_folder = row.get('Directory_Path')
        if not dest_folder: return (index, False, None, None, True)
            
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder, exist_ok=True)
            
        # Use new custom filename generator
        filename = generate_filename(row, format_option=filename_format)
        local_path = os.path.join(dest_folder, filename)
        
        url = row.get('Source_URL')
        doi = row.get('DOI')
        
        downloaded = False
        final_url = url
        
        # 1. Try Existing URL
        if url and str(url).startswith('http') and 'doi.org' not in str(url):
            if download_file(url, local_path):
                return (index, True, url, filename, False)
        
        # 2. Try Unpaywall via DOI
        if doi:
             new_url = get_pdf_from_unpywall(doi)
             if new_url:
                 if download_file(new_url, local_path):
                     return (index, True, new_url, filename, False)

        # 3. Try Meta Tags
        if url and str(url).startswith('http'):
             pdf_url = get_pdf_from_meta_tags(url)
             if pdf_url:
                 if download_file(pdf_url, local_path):
                     return (index, True, pdf_url, filename, False)

        # 4. Secondary Search (S2)
        new_url = attempt_secondary_search(title)
        if new_url:
            if download_file(new_url, local_path):
                 return (index, True, new_url, filename, False)

        # 5. DDG Rescue (Multi-Candidate)
        candidates = attempt_ddg_fallback(title)
        if candidates:
            for cand_url in candidates:
                if download_file(cand_url, local_path):
                     return (index, True, cand_url, filename, False)
        
        return (index, False, None, None, True)

    # --- Execute Parallel Loop ---
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Prepare arguments
    tasks = [(i, row) for i, row in df.iterrows()]
    
    # Max Workers = 5 to avoid triggering aggressive DDoS protection
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_paper = {executor.submit(process_paper_wrapper, task): task for task in tasks}
        
        for future in tqdm(as_completed(future_to_paper), total=len(tasks), desc="Downloading (Parallel)"):
            idx, success, final_url, fname, paywalled = future.result()
            
            if success:
                df.at[idx, 'Is_Downloaded'] = True
                df.at[idx, 'Source_URL'] = final_url
                df.at[idx, 'Original_Filename'] = fname
                df.at[idx, 'Is_Paywalled'] = False
                success_count += 1
                # Optional: print success to keep log alive
                # print(f"   [SUCCESS] {len(str(final_url))} chars") 
            else:
                df.at[idx, 'Is_Downloaded'] = False
                df.at[idx, 'Is_Paywalled'] = True
                fail_count += 1

    print("\nStarting Clean Up and Export...")
    
    unique_paths = df['Directory_Path'].dropna().unique()
    
    # 1. Create JSON Indexes
    for folder_path in unique_paths:
        if not os.path.exists(folder_path): continue
        papers_in_folder = df[df['Directory_Path'] == folder_path]
        index_data = []
        for _, paper in papers_in_folder.iterrows():
            if paper.get('Is_Downloaded', False):
                index_data.append({
                    "Title": paper['Title'],
                    "Authors": paper.get('Authors', 'Unknown'),
                    "Filename": paper.get('Original_Filename'),
                    "Description": paper.get('Description'),
                    "Source_URL": paper.get('Source_URL')
                })
        
        if index_data:
            with open(os.path.join(folder_path, "index.json"), "w") as f:
                json.dump(index_data, f, indent=2)

    # 2. Cleanup Empty Folders
    topic_sanitized = sanitize_folder_name(current_topic)
    topic_root = os.path.join("./Library", topic_sanitized)

    print("Cleaning up target folders...")
    # 1. Clean Leaf Folders (Categories)
    for folder_path in unique_paths:
        if not os.path.exists(folder_path): continue
        try:
            files = os.listdir(folder_path)
            has_pdf = any(f.lower().endswith('.pdf') for f in files)
            # If no PDFs, assume failed category -> nuke it
            if not has_pdf:
                shutil.rmtree(folder_path)
        except Exception: pass

    # 2. Clean Empty Parents (Keywords)
    # Walk bottom-up
    if os.path.exists(topic_root):
        for root, dirs, files in os.walk(topic_root, topdown=False):
            # Ignore root itself
            if root == topic_root: continue
            
            # Check if empty or only .DS_Store
            clean_files = [f for f in files if f != ".DS_Store"]
            if not clean_files and not dirs:
                try:
                     shutil.rmtree(root)
                     print(f"Removed empty folder: {os.path.basename(root)}")
                except: pass

    zip_name = f"Library_{topic_sanitized}"
    
    # 3. Standardize Metadata & Generate Catalogs
    print("Standardizing metadata and generating catalogs...")
    
    standardized_papers = []
    for _, row in df.iterrows():
        # Parse Authors safely
        auth_raw = row.get('Authors', '')
        if pd.isna(auth_raw): auth_raw = ""
        # Assuming comma separated in CSV, but checking given headers
        # Implementation Plan says "join list with semicolon" for CSV output
        # But INPUT is likely comma-separated string from earlier steps?
        # Let's try to split by comma, and clean
        if isinstance(auth_raw, str):
            authors_list = [a.strip() for a in auth_raw.split(',')]
        else:
            authors_list = []
            
        # Parse Year
        pub_date = row.get('Publication_Date', '')
        year = ""
        try:
            if pd.notna(pub_date):
                 year = str(pub_date)[:4]
        except: pass
        
        p_obj = {
            'title': row.get('Title', ''),
            'authors': authors_list,
            'year': year,
            'date': str(row.get('Publication_Date', '')),
            'journal': row.get('_Source', 'Unknown'), # Mapping _Source to Journal/Venue for now
            'doi': row.get('DOI', ''),
            'url': row.get('Source_URL', ''),
            'pdf_url': row.get('Source_URL', '') if str(row.get('Source_URL', '')).endswith('.pdf') else '', # Rough guess
            'abstract': str(row.get('Description', '')) if pd.notna(row.get('Description', '')) else '',
            'citation_count': row.get('Citation_Count', 0),
            'filename': row.get('Original_Filename', ''),
            'category': row.get('Category', 'Uncategorized'),
            'is_downloaded': row.get('Is_Downloaded', False),
            'status': "Downloaded" if row.get('Is_Downloaded') else "Missing/Paywalled"
        }
        standardized_papers.append(p_obj)

    if os.path.exists(topic_root):
        cat_base = os.path.join(topic_root, f"Catalog_{topic_sanitized}")
        
        # A. Markdown
        search_params = {
            "Topics": current_topic,
            "Keywords": kwargs.get('keywords', 'N/A'),
            "Sort Order": sort_by,
            "Limit": limit,
            "Date Range": kwargs.get('date_range', 'All Time')
        }
        create_markdown_catalog(standardized_papers, current_topic, cat_base + ".md", search_params)
        
        # B. CSV
        create_csv_catalog(standardized_papers, cat_base + ".csv")
        
        # C. RIS
        create_ris_catalog(standardized_papers, cat_base + ".ris")
        
        # D. BibTeX (PRP #11)
        create_bibtex_catalog(standardized_papers, cat_base + ".bib")

    # 4. Zip
    if os.path.exists(topic_root):
        shutil.make_archive(zip_name, 'zip', topic_root)
        print(f"READY FOR DOWNLOAD: {zip_name}.zip")
    
    df.to_csv("final_library_catalog.csv", index=False)
    
    print("\n=== Process Complete ===")
    print(f"Successfully downloaded: {success_count} / {len(df)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Max papers to download")
    parser.add_argument("--sort", type=str, default="Most Relevant", help="Sort criteria")
    
    # Metadata Args
    parser.add_argument("--keywords", type=str, default="", help="Keywords used")
    parser.add_argument("--date_start", type=str, default="", help="Start Year")
    parser.add_argument("--date_end", type=str, default="", help="End Year")
    parser.add_argument("--filename_format", type=str, default="Title", help="PDF Filename Format")
    
    args = parser.parse_args()
    
    # Format Date Range
    d_range = "All Time"
    if args.date_start or args.date_end:
        d_range = f"{args.date_start} - {args.date_end}"
    
    # Pass as kwargs
    download_library(
        limit=args.limit, 
        sort_by=args.sort, 
        filename_format=args.filename_format,
        keywords=args.keywords, 
        date_range=d_range
    )
