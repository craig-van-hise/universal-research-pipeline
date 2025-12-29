
import os
from dotenv import load_dotenv
from google import genai
import time

# Load environment
load_dotenv()
key = os.getenv("GOOGLE_API_KEY")

print("\n🧪 EXACT PROMPT REPRODUCTION TEST")
print("================================")

if not key:
    print("❌ ERROR: GOOGLE_API_KEY not found.")
    exit(1)

# Replicating 1_search_omni.py Setup
topic = "Spatial Audio"
prompt = (
    f"The user is researching '{topic}'. Identify the 8 most distinct, high-yield 'Search Verticals' "
    f"for finding papers in this field. \n"
    f"INSTRUCTIONS:\n"
    f"1. Include Broad Synonyms (e.g., if topic is Spatial Audio -> '3D Audio', 'Immersive Audio')\n"
    f"2. Include Core Sub-disciplines (e.g., 'Binaural', 'Ambisonics', 'Wave Field Synthesis')\n"
    f"3. Return ONLY a comma-separated list of 8 terms."
)

print(f"📝 Prompt Config:\nModel: gemini-2.0-flash-001\nLength: {len(prompt)} chars\n")

try:
    # Exact Client Init from Script
    client = genai.Client(api_key=key)
    
    print("🚀 Sending Request...")
    start = time.time()
    resp = client.models.generate_content(model='gemini-2.0-flash-001', contents=prompt)
    duration = time.time() - start
    
    print("\n✅ SUCCESS!")
    print(f"   Response: {resp.text.strip()}")
    print(f"   Latency: {duration:.2f}s")

except Exception as e:
    print("\n❌ REPRODUCTION SUCCESSFUL (IT FAILED)")
    print(f"   Error: {e}")
    # Inspect if there's error details
    if hasattr(e, 'details'):
        print(f"   Details: {e.details()}")
