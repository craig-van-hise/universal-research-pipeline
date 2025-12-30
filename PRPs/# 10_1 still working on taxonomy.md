
### 1. The Strategy: "Forced Adoption"

Currently, if a paper generates a unique category (e.g., "Ambisonic Decoding") but it's the *only* paper in that category, the system marks it as an "orphan" and throws it into Miscellaneous.

**The Fix:** instead of throwing orphans into the trash (Miscellaneous), we will merge them into the **closest existing valid category**.

### 2. The PRP (Product Requirements Prompt)

Copy and paste this PRP into your agent workspace to fix the `src/2_cluster_taxonomy.py` logic.

---

# PRP: Fix "Miscellaneous" Dumping (Orphan Adoption Logic)

**Context:**
The current taxonomy engine is overly aggressive with its "Density Check." If a category has fewer than 2 papers, those papers are currently reassigned to "Miscellaneous." This results in a massive "Miscellaneous" folder containing perfectly good papers that just happened to be in small groups.

**Objective:**
Modify the Orphan Logic. Instead of dumping small groups into "Miscellaneous," we should:

1. **Keep** small categories if they are highly specific (Size = 1 is okay if the name is technical).
2. **Force-Assign** orphans to the "Next Best" category if possible, rather than "Miscellaneous."

**Target File:** `src/2_cluster_taxonomy.py`

## 🛠️ Engineering Requirements

### 1. Relax Density Thresholds

In `cluster_and_categorize`, locate the section labeled **"Enforce Orphan Rules"** (or similar density check logic).

**Change the Logic to:**

* **Threshold:** Reduce the minimum density from `2` to `1`.
* **Rule:** If a category has at least 1 paper, **KEEP IT**.
* **Reasoning:** It is better to have a folder named "Ambisonic Decoding" with 1 paper than a folder named "Miscellaneous" with 20 unrelated papers.

### 2. The "General" Fallback (The Safety Net)

* **Logic:** Only use "Miscellaneous" if the LLM explicitly returned "General" or failed to output JSON.
* **Implementation:** Remove the code block that iterates through `orphans` and reassigns them to `general_cat`.

### 3. Implementation Plan (Code Replacement)

**Find this block (or similar):**

```python
# Old Logic (DELETE THIS)
counts = Counter(taxonomy_map.values())
orphans = [cat for cat, count in counts.items() if count < 2]
if orphans:
    for doc_id, cat in taxonomy_map.items():
        if cat in orphans:
            taxonomy_map[doc_id] = "Miscellaneous"

```

**Replace with this (KEEP EVERYTHING):**

```python
# New Logic: No Orphan Reassignment
# We accept singleton categories to prevent "Miscellaneous" bloating.
counts = Counter(taxonomy_map.values())
print(f"DEBUG: Category Distribution: {counts}") 
# (No re-assignment code here)

```

## ✅ Definition of Done

1. **Zero False Miscellaneous:** A paper is only in "Miscellaneous" if the LLM truly could not categorize it.
2. **Singleton Folders Allowed:** You will likely see folders with 1 PDF. This is acceptable and preferred over the current behavior.

