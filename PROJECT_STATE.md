# Project Status Report

**Date:** 2025-12-28
**Status:** Operational / Stable
**Current Phase:** Search Optimization & Alert System Implementation

## Executive Summary
**ScholarStack** (formerly Universal Research Librarian) has been updated with parallelized search capabilities and refined filtering logic to handle high-volume scraping. The immediate focus is resolving search bottlenecks caused by paywalls and implementing a "Scholar-Alert" email notification system.

## Implemented Architecture

### 1. The Omni-Search Module (`1_search_omni.py`) (V10)
*   **Parallel Processing:** Uses `ThreadPoolExecutor` to check Unpaywall accessibility for 20+ papers concurrently, significantly reducing wait times.
*   **Recall Optimization:** Removed redundant client-side keyword filtering. The system now trusts the Search API's relevance (Full Text) even if metadata abstracts are missing, resolving the "Low Yield" issue.
*   **Speed Optimization:** Enabled `openAccessPdf` server-side filtering for Semantic Scholar to eliminate useless checks on paywalled papers.
*   **Logic Toggle:** User can now choose between "Match Any" (OR) and "Match All" (AND) keyword logic.

### 2. The Interface (`app.py`)
*   **Branding:** Renamed app to "ScholarStack: Your AI Research Librarian".
*   **Simplification:** Removed manual API Key input; keys are now managed via Environment Variables.
*   **Feedback:** Search logs stream in real-time, showing detailed "Accepted/Rejected" status.

### 3. Core Pipeline
*   **Target Logic:** "Fill the Bucket" loop continues until target count is met.
*   **Sources:** Crossref (Deep Search) + Semantic Scholar (High Precision/OA).

## Validated Fixes
*   **Zero Results:** Fixed by relaxing local keyword constraints (Semantic Scholar now yielding papers).

## Known Issues (Critical)
*   **Persistent Low Yield:** Despite Hybrid Search and Topic Expansion, the number of *accepted* papers remains low (single digits instead of hundreds). The search pipeline is technically sound but operationally inefficient at finding high-volume relevant results.
*   **Search Slowness:** Deep searching logic (Pass 1 + Pass 2) is slow.
*   **Search Methods:** Still require significant tuning and optimization.

## Recent Accomplishments
*   **API Stability:** Resolved persistent "Quota Exceeded" errors by implementing a **Persistence Loop** (wait & retry) for the Gemini API and fixing a critical environment variable mismatch using `load_dotenv(override=True)`.
*   **Search Vertical Expansion:** Successfully implemented LLM-driven "Search Verticals" (e.g., Topic -> Sub-disciplines) to maximize OpenAlex recall.
*   **Hybrid Search Integration:** Implemented BM25 + Vector Search (ChromaDB) to resolve topics.
*   **Topic Expansion:** Uses LLM to generate synonyms for broader search recall.
*   **Dynamic Model Selection:** System now auto-detects the best available Gemini Flash model.

## Resolved Issues
*   **LLM Quota Errors:** Traced to a stale shell environment variable. Fixed by forcing the script to reload `.env`.
*   **Search Hangs:** Fixed by implementing proper API backoff and logging.

## Upcoming Features
*   **Search Yield Optimization:** Tuning the "Backdoor" algorithm to increase the volume of accepted papers based on the now-stable Search Verticals.
