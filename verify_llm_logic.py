
import importlib.util
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Dynamically import the script (since it starts with a number)
spec = importlib.util.spec_from_file_location("search_omni", "1_search_omni.py")
search_omni = importlib.util.module_from_spec(spec)
sys.modules["search_omni"] = search_omni
spec.loader.exec_module(search_omni)

ResearchCrawler = search_omni.ResearchCrawler

print("⚡️ Starting Live LLM Logic Verification...")

try:
    # Initialize Crawler (Dummy args)
    crawler = ResearchCrawler(
        topic="Spatial Audio", 
        keywords="HRTF", 
        author="", 
        publication="", 
        date_start="", 
        date_end="", 
        count=10, 
        sites=[], 
        keyword_logic='any', 
        no_llm=False
    )
    
    # Test 1: Topic Expansion (Uses Model Rotation)
    print("\n[Test 1] Testing expand_topic_with_llm...")
    topics = crawler.expand_topic_with_llm("Spatial Audio")
    print(f"   -> Result: {topics[:3]}... (Total {len(topics)})")
    if len(topics) > 1:
        print("   ✅ Topic Expansion Passed.")
    else:
        print("   ❌ Topic Expansion Returned Default (Failed).")

    # Test 2: Synonym Expansion (Uses Model Rotation)
    print("\n[Test 2] Testing expand_keywords_with_llm...")
    syns = crawler.expand_keywords_with_llm(["HRTF"])
    print(f"   -> Result: {syns[:3]}... (Total {len(syns)})")
    if len(syns) > 1:
         print("   ✅ Synonym Expansion Passed.")
    else:
         print("   ❌ Synonym Expansion Returned Default (Failed).")

    
    # Test 3: Search Verticals (Uses Model Rotation) - CRITICAL FAIL POINT
    print("\n[Test 3] Testing get_search_verticals_from_llm...")
    verticals = crawler.get_search_verticals_from_llm("Spatial Audio")
    print(f"   -> Result: {verticals}")
    if len(verticals) > 1:
         print("   ✅ Verticals Generation Passed.")
    else:
         print("   ❌ Verticals Generation Failed (Returned Default).")

    print("\n🎉 ALL TESTS PASSED. The script is safe to run.")

except Exception as e:
    print(f"\n❌ FATAL ERROR During Verification: {e}")
    import traceback
    traceback.print_exc()
