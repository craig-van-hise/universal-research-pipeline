
import sys
import os
import requests
import pandas as pd
from tqdm import tqdm

# Add parent directory to path so we can import from 3_download_library
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from library_downloader import attempt_ddg_fallback, attempt_secondary_search
except ImportError:
    # Try importing directly if the file is named 3_download_library.py
    # We might need to rename it or dynamic import to test it properly without renaming
    import importlib.util
    spec = importlib.util.spec_from_file_location("library_downloader", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "3_download_library.py"))
    library_downloader = importlib.util.module_from_spec(spec)
    sys.modules["library_downloader"] = library_downloader
    spec.loader.exec_module(library_downloader)
    attempt_ddg_fallback = library_downloader.attempt_ddg_fallback
    attempt_secondary_search = library_downloader.attempt_secondary_search


MISSING_PAPERS = [
    "Influence of height-channel contents on enhancing spatial impressions through virtually elevated loudspeaker",
    "A Spatial Audio System Using Multiple Microphones on a Rigid Sphere",
    "Recent Advances in an Open Software for Numerical HRTF Calculation",
    "A Unified Approach To Numerical Auditory Scene Synthesis Using Loudspeaker Arrays",
    "Sound Source and Loudspeaker Base Angle Dependency of Phantom Image Elevation Effect",
    "The SONICOM HRTF Dataset"
]

def test_retrieval_logic():
    print(f"=== TEST SUITE: Resolving {len(MISSING_PAPERS)} Missing Papers ===")
    
    # Import download_file
    try:
        download_file = library_downloader.download_file
    except AttributeError:
        # Fallback if import weirdness
        def download_file(url, path):
            try:
                r = requests.get(url, timeout=10, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code == 200 and b'%PDF' in r.content[:1024]:
                    return True
            except: pass
            return False

    results = []
    
    
        
    for title in MISSING_PAPERS:
        print(f"\n🔎 Testing: {title}")
        
        found_url = False
        download_success = False
        method = None
        final_url = None
        
        # 1. Secondary Search (Semantic Scholar)
        url = attempt_secondary_search(title)
        
        if url:
             print(f"   [Secondary] Found: {url}")
             # Try Download
             temp_path = f"temp_test_{abs(hash(title))}.pdf"
             if download_file(url, temp_path):
                 download_success = True
                 method = "Secondary"
                 final_url = url
                 print(f"   -> 💾 Secondary Search SUCCESS")
                 if os.path.exists(temp_path): os.remove(temp_path)
             else:
                 print(f"   -> ❌ Secondary Download FAILED (proceeding to fallback)")
                 
        # 2. DDG Fallback (if Secondary failed search OR download)
        if not download_success:
            candidates = attempt_ddg_fallback(title)
            if candidates:
                for cand_url in candidates:
                    print(f"   [DDG] Candidate: {cand_url}")
                    temp_path = f"temp_test_{abs(hash(title))}.pdf"
                    if download_file(cand_url, temp_path):
                        download_success = True
                        method = "DDG"
                        final_url = cand_url
                        print(f"   -> 💾 DDG Search SUCCESS")
                        if os.path.exists(temp_path): os.remove(temp_path)
                        break
                    else:
                        print(f"   -> ❌ DDG Download FAILED (Candidate Failed)")


        results.append({
            "title": title,
            "found_url": final_url is not None,
            "download_success": download_success,
            "method": method,
            "url": final_url
        })
        
    # Summary
    found_count = len([r for r in results if r['found_url']])
    downloaded_count = len([r for r in results if r['download_success']])
    
    print("\n" + "="*40)
    print(f"SUMMARY: {downloaded_count}/{len(MISSING_PAPERS)} Papers Fully Resolved (Downloaded)")
    print(f"         {found_count}/{len(MISSING_PAPERS)} URLs Found")
    print("="*40)
    
    if downloaded_count < len(MISSING_PAPERS) * 0.5:
        print("❌ FAILURE: Download rate < 50%")
        sys.exit(1)
    else:
        print("✅ SUCCESS: Download rate >= 50%")
        sys.exit(0)

if __name__ == "__main__":
    test_retrieval_logic()
