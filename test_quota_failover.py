
import importlib.util
import sys
import unittest
from unittest.mock import MagicMock, patch

# Dynamically import the script
spec = importlib.util.spec_from_file_location("search_omni", "1_search_omni.py")
search_omni = importlib.util.module_from_spec(spec)
sys.modules["search_omni"] = search_omni
spec.loader.exec_module(search_omni)

ResearchCrawler = search_omni.ResearchCrawler

class TestQuotaFailover(unittest.TestCase):
    def setUp(self):
        self.crawler = ResearchCrawler(
            topic="Spatial Audio", keywords="HRTF", author="", publication="", 
            date_start="", date_end="", count=10, sites=[], no_llm=False
        )

    def test_verticals_quota_exhaustion(self):
        print("\n⚡️ TEST: Simulating Global 429 Quota Exhaustion...")
        
        # Mock the client and generate_content to raise Exception
        mock_client = MagicMock()
        mock_models = MagicMock()
        # Side effect: always raise Exception with "429"
        mock_models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: You have exceeded your quota.")
        mock_client.models = mock_models
        
        # Patch get_genai_client to return our mock
        with patch.object(self.crawler, 'get_genai_client', return_value=mock_client):
            # Patch time.sleep to run fast
            with patch('time.sleep', return_value=None):
                verticals = self.crawler.get_search_verticals_from_llm("Spatial Audio")
                
        print(f"   -> Resulting Verticals: {verticals}")
        
    def test_global_circuit_breaker(self):
        print("\n⚡️ TEST: Verifying Circuit Breaker (Auto-Kill LLM)...")
        # Ensure LLM is on initially
        self.crawler.no_llm = False
        
        mock_client = MagicMock()
        mock_models = MagicMock()
        # First call triggers RESOURCE_EXHAUSTED
        mock_models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
        mock_client.models = mock_models
        
        with patch.object(self.crawler, 'get_genai_client', return_value=mock_client):
            with patch('time.sleep', return_value=None): # Speed up first fail
                # Call 1: Should trigger kill switch
                self.crawler._query_llm_with_rotation("test")
                
        # Assert kill switch is active
        if self.crawler.no_llm:
            print("   ✅ Circuit Breaker ACTIVATED: no_llm is now True.")
        else:
            print("   ❌ Circuit Breaker FAILED: no_llm is still False.")
            self.fail("Circuit breaker failed.")
            
        # Call 2: Should return None immediately (mock not called)
        with patch.object(self.crawler, 'get_genai_client') as mock_get_client:
             res = self.crawler._query_llm_with_rotation("test 2")
             if res is None and not mock_get_client.called:
                 print("   ✅ Short-Circuit Logic WORKS: API not called.")
             else:
                 print("   ❌ Short-Circuit Logic FAILED.")

if __name__ == '__main__':
    unittest.main()
