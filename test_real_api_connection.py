
import os
from dotenv import load_dotenv
from google import genai
import time

# Load environment
load_dotenv()

key = os.getenv("GOOGLE_API_KEY")

print("\n🔍 API DIAGNOSTIC UTIL")
print("=======================")

if not key:
    print("❌ ERROR: GOOGLE_API_KEY not found in environment.")
    exit(1)

print(f"🔑 Key loaded: {key[:8]}...{key[-4:]} (Length: {len(key)})")
print("   (Please compare this prefix with the credentials in your Google Cloud Console)\n")

print("📡 Attempting connection to 'gemini-2.0-flash-001'...")

try:
    client = genai.Client(api_key=key)
    prompt = "Hello. Reply with 'OK'."
    
    start = time.time()
    response = client.models.generate_content(model='gemini-2.0-flash-001', contents=prompt)
    duration = time.time() - start
    
    print("\n✅ SUCCESS!")
    print(f"   Response: {response.text.strip()}")
    print(f"   Latency: {duration:.2f}s")
    
    # Try to inspect usage metadata if available
    if hasattr(response, 'usage_metadata'):
        print(f"   Usage Metadata: {response.usage_metadata}")

except Exception as e:
    print("\n❌ FAILURE / QUOTA HIT")
    print(f"   Type: {type(e).__name__}")
    print(f"   Message: {e}")
    # Print full details if it's an API error
    if hasattr(e, 'message'):
        print(f"   Full Details: {e.message}")
