import subprocess
import os
import sys
import tempfile
import shutil

def run_full_pipeline(topic, keywords=None, author=None, publication=None, 
                      date_start=None, date_end=None, sites=None, count=10, 
                      sort_method="Most Relevant", google_api_key=None, keyword_logic='any',
                      auto_folders=True, use_keywords=False, filename_format="Title"):
    """
    Orchestrates the full research pipeline in an isolated temporary directory.
    Yields log lines for real-time UI updates.
    Returns the path to the final zip file.
    """
    
    # 1. Setup Isolation Chamber (Temp Directory)
    # This ensures multiple users don't overwrite each other's files
    temp_dir = tempfile.mkdtemp(prefix="urp_mission_")
    current_dir = os.getcwd()
    
    # Get absolute paths to the scripts (since we will change execution context)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_1 = os.path.join(base_dir, "1_search_omni.py")
    script_2 = os.path.join(base_dir, "2_cluster_taxonomy.py")
    script_3 = os.path.join(base_dir, "3_download_library.py")
    
    yield f"🚀 Starting Mission in Isolated Workspace..."
    # yield f"DEBUG: Workspace: {temp_dir}"

    # Prepare environment with API key
    env = os.environ.copy()
    if google_api_key:
        env["GOOGLE_API_KEY"] = google_api_key

    try:
        # --- Phase 1: Search ---
        yield f"--- Starting Phase 1: Search (Topic: {topic}) ---"
        
        # Buffer the search count to account for Phase 2 filtering/deduplication
        buffered_count = int(int(count) * 1.5) + 5
        search_cmd = [
            sys.executable, script_1,
            "--topic", topic,
            "--count", str(buffered_count)
        ]
        
        if keywords:
            search_cmd.extend(["--keywords", keywords])
        if author:
            search_cmd.extend(["--author", author])
        if publication:
            search_cmd.extend(["--publication", publication])
        if date_start:
            search_cmd.extend(["--date_start", date_start])
        if date_end:
            search_cmd.extend(["--date_end", date_end])
        if sites:
            sites_str = ",".join(sites)
            search_cmd.extend(["--sites", sites_str])
        
        if keyword_logic:
            search_cmd.extend(["--keyword_logic", keyword_logic])

        # Execute inside temp_dir
        process = subprocess.Popen(
            search_cmd, 
            cwd=temp_dir,
            env=env,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1
        )
        
        for line in process.stdout:
            yield line.strip()
        
        process.wait()
        if process.returncode != 0:
            yield "❌ Phase 1 Failed."
            return None
        yield "✅ Phase 1 Complete."

        # --- Phase 2: Cluster & Categorize ---
        yield "--- Starting Phase 2: AI Clustering ---"
        
        cluster_cmd = [
            sys.executable, script_2,
            "--topic", topic,
            "--sort", sort_method,
            "--limit", str(count)
        ]
        
        if not auto_folders:
            cluster_cmd.append("--no_llm")
        
        if use_keywords:
            cluster_cmd.append("--use_keywords")
        
        process = subprocess.Popen(
            cluster_cmd, 
            cwd=temp_dir,
            env=env,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1
        )
        
        for line in process.stdout:
            yield line.strip()
            
        process.wait()
        if process.returncode != 0:
            yield "❌ Phase 2 Failed."
            return None
        yield "✅ Phase 2 Complete."

        # --- Phase 3: Download & Export ---
        yield "--- Starting Phase 3: Download & Export ---"
        
        download_cmd = [
            sys.executable, script_3,
            "--limit", str(count),
            "--sort", sort_method,
            "--filename_format", filename_format
        ]
        
        # Pass metadata strings
        if keywords:
            download_cmd.extend(["--keywords", keywords])
            
        if date_start:
            download_cmd.extend(["--date_start", str(date_start)])
        if date_end:
            download_cmd.extend(["--date_end", str(date_end)])
        
        process = subprocess.Popen(
            download_cmd, 
            cwd=temp_dir,
            env=env,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1
        )
        
        for line in process.stdout:
            yield line.strip()
            
        process.wait()
        if process.returncode != 0:
            yield "❌ Phase 3 Failed."
            return None
        yield "✅ Phase 3 Complete."
        
        # Check for final catalog to render timeline
        final_csv = os.path.join(temp_dir, "final_library_catalog.csv")
        if os.path.exists(final_csv):
             yield ("CATALOG_CSV", final_csv)

        # --- Validate Output ---
        # Find the zip file in the temp dir
        # The script creates "ScholarStack_{SanitizedTopic}.zip"
        # We don't know the exact sanitization logic of the script perfectly here,
        # so we look for any .zip file.
        
        zip_file = None
        for f in os.listdir(temp_dir):
            if f.endswith(".zip"):
                zip_file = os.path.join(temp_dir, f)
                break
        
        if zip_file and os.path.exists(zip_file):
            yield f"🎉 Pipeline Success! Output ready."
            yield ("RETURN_PATH", zip_file) # Pass the temp path back
            yield ("TEMP_DIR", temp_dir)    # Pass temp dir so app can cleanup later? 
                                            # Actually app reads immediately.
                                            # We rely on OS to cleanup /tmp or do it manually later.
        else:
            yield "⚠️ Pipeline finished, but zip file was not found."
            return None

    except Exception as e:
        yield f"❌ Critical Pipeline Error: {e}"
        return None

if __name__ == "__main__":
    print("Running Test Pipeline...")
    gen = run_full_pipeline("Audio Inpainting", count=5, sites=['arxiv'])
    for line in gen:
        print(line)
