import pandas as pd
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import os
import re
import json
import shutil
from urllib.parse import urlparse, unquote
from tqdm import tqdm
import time
import random
from bs4 import BeautifulSoup
from googlesearch import search
from unpywall import Unpywall
from unpywall.utils import UnpywallCredentials
UnpywallCredentials('vv@scholar-stack.com') # Using user email logic or placeholder

def sanitize_filename(name):
    """Sanitizes filenames to be OS-safe."""
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_filename_from_cd(cd):
    """Get filename from content-disposition header."""
    if not cd:
        return None
    fname = re.findall(r'filename=["\']?([^"\';]+)["\']?', cd)
    if len(fname) == 0:
        return None
    return fname[0].strip()

def create_markdown_catalog(df, topic, output_path):
    """Generates a human-readable Markdown catalog."""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Library Catalog: {topic}\n\n")
        f.write(f"**Total Papers:** {len(df)}\n")
        f.write(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        for category, group in df.groupby('Category'):
            f.write(f"## {category}\n\n")
            
            for _, row in group.iterrows():
                title = row.get('Title', 'Unknown Title')
                authors = row.get('Authors', 'Unknown Authors')
                date = str(row.get('Publication_Date', 'Unknown Date'))
                status = "Downloaded" if row.get('Is_Downloaded') else "Missing/Paywalled"
                filename = row.get('Original_Filename', 'N/A')
                url = row.get('Source_URL', '#')
                desc = str(row.get('Description', ''))
                
                if len(desc) > 200:
                    desc = desc[:200] + "..."
                desc = desc.replace('\n', ' ')

                f.write(f"*   **{title}** ({date})\n")
                f.write(f"    *   *Authors:* {authors}\n")
                f.write(f"    *   *Status:* {status}\n")
                if row.get('Is_Downloaded'):
                    f.write(f"    *   *Filename:* `{filename}`\n")
                f.write(f"    *   *Source:* [Link]({url})\n")
                f.write(f"    *   *Abstract:* {desc}\n\n")

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
    """Scrapes landing page for <meta name='citation_pdf_url'>."""
    if not url or 'pdf' in url.lower(): return None
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'html.parser')
            # Standard Google Scholar tag
            meta_pdf = soup.find('meta', attrs={'name': 'citation_pdf_url'})
            if meta_pdf and meta_pdf.get('content'):
                candidate = meta_pdf['content']
                # TU-Berlin Bug Fix: They return 'localhost' in meta tags sometimes
                if 'localhost' in candidate and 'tu-berlin' in url:
                    candidate = candidate.replace('http://localhost:4000', 'https://depositonce.tu-berlin.de')
                print(f"   [Meta Scraper] Found PDF: {candidate}")
                return candidate
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
            r = requests.get('https://api.semanticscholar.org/graph/v1/paper/search', params=params, timeout=10)
            
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
        
    time.sleep(2) # Politeness delay
    return None

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
    for attempt in range(3):
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
            r = requests.get(url, headers=headers, stream=True, timeout=20, verify=False)
            
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

def download_library(limit=None, sort_by="Most Relevant"):
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
    # else: "Most Relevant" -> assumes input order is relevance (from API)

    # 2. Trim
    if limit:
        original_count = len(df)
        df = df.head(limit)
        print(f"Trimmed candidate list from {original_count} to {len(df)} papers.")
    
    success_count = 0
    fail_count = 0
    
    print(f"Found {len(df)} papers. Starting download process...")

    for index, row in tqdm(df.iterrows(), total=len(df), desc="Downloading"):
        url = row.get('Source_URL')
        doi = row.get('DOI')
        
        # --- ROBUST URL RESOLUTION STRATEGY ---
        # 1. Clean Landing Page URL? Use Scraper
        if url and 'doi.org' in str(url):
             meta_url = get_pdf_from_meta_tags(url)
             if meta_url: 
                 url = meta_url
                 df.at[index, 'Source_URL'] = meta_url
                 
        # 2. If Scraper Failed (or no URL), try Unpywall
        if pd.isna(url) or 'doi.org' in str(url) or not str(url).startswith('http'):
             new_url = get_pdf_from_unpywall(doi)
             if new_url: 
                 url = new_url
                 df.at[index, 'Source_URL'] = new_url 

        # 3. Final Check
        if pd.isna(url) or not str(url).startswith('http'):
            # --- NEW: SECONDARY SEARCH (Deep Rescue) ---
            new_url = attempt_secondary_search(row.get('Title'))
            if new_url:
                url = new_url
                df.at[index, 'Source_URL'] = new_url
            else:
                 # --- NEW: TERTIARY SEARCH (Nuclear Option) ---
                 google_url = attempt_google_fallback(row.get('Title'))
                 if google_url:
                     url = google_url
                     df.at[index, 'Source_URL'] = google_url
                 else:
                     continue
            
        dest_folder = row.get('Directory_Path')
        if not dest_folder: continue
            
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder, exist_ok=True)
            
        title = row.get('Title', 'Unknown_Paper')
        
        # Determine Filename
        filename = "document.pdf"
        try:
            # Try to get cleaner name from URL first
            parsed_url = urlparse(url)
            base = os.path.basename(unquote(parsed_url.path))
            if base and base.lower().endswith('.pdf'):
                filename = base
            
            filename = sanitize_filename(filename)
            name_part, ext = os.path.splitext(filename)
            
            # Ensure it ends in .pdf
            if not ext: 
                filename += ".pdf"
            
            # Prevent generic overwrites or bad names
            if len(name_part) < 4 or name_part.lower() in ['document', 'file', 'download', 'view']:
                safe_title = sanitize_filename(title)[:40].replace(' ', '_')
                filename = f"{safe_title}.pdf"
        except:
            filename = "document.pdf"

        local_path = os.path.join(dest_folder, filename)
        
        # Execute Download
        if download_file(url, local_path):
            df.at[index, 'Is_Downloaded'] = True
            df.at[index, 'Original_Filename'] = filename
            df.at[index, 'Is_Paywalled'] = False
            success_count += 1
        else:
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
    print("Cleaning up target folders...")
    for folder_path in unique_paths:
        if not os.path.exists(folder_path): continue
        try:
            files = os.listdir(folder_path)
            has_pdf = any(f.lower().endswith('.pdf') for f in files)
            if not has_pdf:
                shutil.rmtree(folder_path)
        except Exception: pass

    topic_sanitized = sanitize_folder_name(current_topic)
    topic_root = os.path.join("./Library", topic_sanitized)
    zip_name = f"Library_{topic_sanitized}"
    
    # 3. Catalog (BEFORE Zip)
    print("Generating Library Catalog...")
    df = df.sort_values(by='Category')
    if os.path.exists(topic_root):
        catalog_path = os.path.join(topic_root, f"Catalog_{topic_sanitized}.md")
        create_markdown_catalog(df, current_topic, catalog_path)

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
    args = parser.parse_args()
    
    download_library(limit=args.limit, sort_by=args.sort)
