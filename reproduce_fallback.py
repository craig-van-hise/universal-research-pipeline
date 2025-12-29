
import requests
from bs4 import BeautifulSoup
import random

def test_download(url, name):
    print(f"Testing {name}: {url}")
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    headers = {'User-Agent': random.choice(user_agents)}
    
    try:
        # 1. Direct GET
        r = requests.get(url, headers=headers, timeout=10, stream=True)
        print(f"   Status: {r.status_code}")
        print(f"   Content-Type: {r.headers.get('Content-Type')}")
        
        # 2. If it's HTML, try to scrape meta tag
        if 'text/html' in r.headers.get('Content-Type', '').lower():
            soup = BeautifulSoup(r.content, 'html.parser')
            meta_pdf = soup.find('meta', attrs={'name': 'citation_pdf_url'})
            if meta_pdf:
                res = meta_pdf['content']
                if 'localhost' in res:
                    res = res.replace('http://localhost:4000', 'https://depositonce.tu-berlin.de')
                    print(f"   [FIXED] Found Meta PDF: {res}")
                else:
                    print(f"   Found Meta PDF: {res}")
            else:
                print("   No Meta PDF tag found.")
                
            # specific scrapers
            if 'depositonce' in url:
                # Look for file download link in DSpace/DepositOnce
                # Common pattern: <a href="/bitstream/...">
                for a in soup.find_all('a', href=True):
                    if 'bitstream' in a['href'] and a['href'].endswith('.pdf'):
                        print(f"   Found Bitstream PDF: {a['href']}")
                        
    except Exception as e:
        print(f"   Error: {e}")
    print("-" * 30)

if __name__ == "__main__":
    test_cases = [
        ("http://depositonce.tu-berlin.de/handle/11303/183", "TU-Berlin"),
        ("https://www.ioa.org.uk/system/files/proceedings/j_hollebon_e_c_hamdan_dr_f_m_fazi_a_comparison_of_the_performance_of_hrtf_models.pdf", "IOA PDF"),
        ("https://research.chalmers.se/en/publication/512402", "Chalmers"),
        ("https://www.mdpi.com/2076-3417/7/6/627/pdf?version=1497700319", "MDPI")
    ]
    
    for url, name in test_cases:
        test_download(url, name)
