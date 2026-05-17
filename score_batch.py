import re
import json
import sys

# Read the prompt file with UTF-8 encoding
with open(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude\scratch\batch_0089_prompt.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Split documents
docs_section = content.split("## Documents to Score\n")[1] if "## Documents to Score" in content else content
doc_blocks = re.split(r'^--- DOCUMENT \d+ ---', docs_section, flags=re.MULTILINE)[1:]

# Extract doc info
results = []
for block in doc_blocks:
    # Extract doc_id
    doc_id_match = re.search(r'doc_id: ([a-f0-9]+)', block)
    if not doc_id_match:
        continue
    doc_id = doc_id_match.group(1)
    
    # Extract full document text for analysis (lowercase for matching)
    doc_text_lower = block.lower()
    
    # SCORING LOGIC
    # score_carefirst: Look for care-first programs and initiatives
    score_carefirst = 0
    carefirst_keywords = ['care-first', 'measure j', 'cfci', 'youth development', 'diversion', 'reentry', 'ready to rise', 'youth justice']
    carefirst_count = sum(1 for kw in carefirst_keywords if kw in doc_text_lower)
    if carefirst_count >= 3:
        score_carefirst = 10
    elif carefirst_count == 2:
        score_carefirst = 7
    elif carefirst_count == 1:
        score_carefirst = 4
    else:
        score_carefirst = 0
    
    # score_ai_governance: Look for AI/tech governance references
    score_ai_governance = 0
    ai_keywords = ['ai', 'algorithm', 'technology', 'tech', 'digital', 'genai', 'machine learning', 'automation', 'cio', 'isd']
    ai_count = sum(1 for kw in ai_keywords if kw in doc_text_lower)
    if ai_count >= 5:
        score_ai_governance = 10
    elif ai_count >= 3:
        score_ai_governance = 6
    elif ai_count >= 1:
        score_ai_governance = 3
    else:
        score_ai_governance = 0
    
    # score_intersection: Look for connections between care-first and AI/tech
    score_intersection = 0
    has_carefirst = any(kw in doc_text_lower for kw in carefirst_keywords)
    has_ai = any(kw in doc_text_lower for kw in ai_keywords)
    
    if has_carefirst and has_ai:
        score_intersection = 4
    elif has_carefirst or has_ai:
        score_intersection = 2
    else:
        score_intersection = 0
    
    # score_evidentiary: Count named officials and dollar amounts
    score_evidentiary = 0
    # Count officials (looking for titles and names)
    official_patterns = [
        r'Supervisor\s+[A-Z][a-z]+',
        r'Director',
        r'Chair(?:person)?',
        r'CEO',
        r'CIO'
    ]
    official_count = sum(len(re.findall(pat, block)) for pat in official_patterns)
    score_evidentiary += min(official_count, 3)
    
    # Count dollar amounts
    dollar_count = len(re.findall(r'\$[\d,]+', block))
    score_evidentiary += min(dollar_count, 2)
    
    score_evidentiary = min(score_evidentiary, 10)
    
    # Rationale
    rationale = f"care-first:{score_carefirst} ai:{score_ai_governance} intersection:{score_intersection} evid:{score_evidentiary}"
    
    results.append({
        "doc_id": doc_id,
        "score_carefirst": score_carefirst,
        "score_ai_governance": score_ai_governance,
        "score_intersection": score_intersection,
        "score_evidentiary": score_evidentiary,
        "rationale": rationale
    })

# Write results
output_path = r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude\scratch\batch_0089_result.json"
with open(output_path, 'w') as f:
    json.dump(results, f)

print(f"Scored {len(results)} documents")
