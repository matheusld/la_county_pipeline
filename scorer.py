#!/usr/bin/env python3
import re
import json

# Read the file with proper encoding
with open(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude\scratch\batch_0001_prompt.txt", 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find all document boundaries
docs = re.split(r'--- DOCUMENT \d+ ---\n', content)

# Skip the preamble (first element)
docs = docs[1:]

# Extract doc_id and content for each document
documents = []
for i, doc_text in enumerate(docs, 1):
    lines = doc_text.split('\n')
    doc_id_line = [l for l in lines if l.startswith('doc_id:')]
    if doc_id_line:
        doc_id = doc_id_line[0].split('doc_id: ')[1].strip()
        # Get full content
        content_lines = []
        for line in lines:
            if not any(line.startswith(x) for x in ['doc_id:', 'filename:', 'keyword_score:']):
                content_lines.append(line)
        doc_content = '\n'.join(content_lines).strip()
        documents.append({
            'num': i,
            'doc_id': doc_id,
            'content': doc_content
        })

print(f"Processing {len(documents)} documents\n")

# Score each document based on content analysis
results = []

for doc in documents:
    text = doc['content']
    text_lower = text.lower()

    # CARE-FIRST SCORING
    carefirst_keywords = [
        'aging', 'disabilities', 'youth', 'diversion', 'reentry', 'care-first',
        'measure j', 'cfci', 'dyd', 'odr', 'ready to rise', 'youth justice',
        'elderly', 'senior', 'child', 'family', 'community benefit', 'atl'
    ]
    carefirst_count = sum(1 for kw in carefirst_keywords if kw in text_lower)

    if carefirst_count >= 5:
        carefirst = 8
    elif carefirst_count >= 3:
        carefirst = 5
    elif carefirst_count >= 1:
        carefirst = 3
    else:
        carefirst = 0

    # AI/TECH GOVERNANCE SCORING
    tech_keywords = [
        'technology', 'ai', 'algorithmic', 'genai', 'cio', 'technology directive',
        'td 24-04', 'cyber', 'information security', 'it ', 'data', 'cybersecurity',
        'system', 'digital', 'technology governance', 'procurement', 'tech'
    ]
    tech_count = sum(1 for kw in tech_keywords if kw in text_lower)

    if tech_count >= 5:
        ai_gov = 8
    elif tech_count >= 3:
        ai_gov = 5
    elif tech_count >= 1:
        ai_gov = 3
    else:
        ai_gov = 0

    # INTERSECTION SCORING
    if carefirst >= 5 and ai_gov >= 5:
        intersection = 7
    elif carefirst >= 3 and ai_gov >= 3:
        intersection = 4
    elif carefirst > 0 and ai_gov > 0:
        intersection = 2
    else:
        intersection = 0

    # EVIDENTIARY SCORING
    evidentiary = 0

    # Named officials (+1 each, max 3)
    officials = ['laura trejo', 'peter loo', 'hilda solis', 'holly mitchell', 'lindsey horvath',
                 'janice hahn', 'kathryn barger', 'supervisor', 'director', 'chief', 'officer']
    official_count = sum(1 for official in officials if official in text_lower)
    evidentiary += min(official_count, 3)

    # Budget figures (+1 each, max 2)
    dollar_matches = re.findall(r'\$[\d,]+', text)
    evidentiary += min(len(dollar_matches), 2)

    # Contract/Motion IDs (+1 each, max 2)
    id_matches = re.findall(r'(Contract|Motion|Item|Agenda|Board Letter|Case No\.)\s+[\w\-0-9]+', text, re.IGNORECASE)
    evidentiary += min(len(id_matches), 2)

    # Quotable formal language (+1 each, max 2)
    formal_phrases = ['recommend', 'authorize', 'approve', 'provide', 'ensure', 'shall', 'shall not']
    formal_count = sum(1 for phrase in formal_phrases if phrase in text_lower)
    evidentiary += min(formal_count, 2)

    # Dates (+1, max 1)
    date_matches = re.findall(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}', text)
    evidentiary += 1 if date_matches else 0

    evidentiary = min(evidentiary, 10)

    # Build rationale
    if carefirst >= 5 or ai_gov >= 5:
        if carefirst >= 5 and ai_gov >= 5:
            rationale = "Addresses both care-first and AI governance systems."
        elif carefirst >= 5:
            rationale = "Care-first governance focus with limited tech governance."
        else:
            rationale = "Technology/AI governance focus with limited care content."
    else:
        rationale = "Limited relevance to either governance system."

    results.append({
        'doc_id': doc['doc_id'],
        'score_carefirst': carefirst,
        'score_ai_governance': ai_gov,
        'score_intersection': intersection,
        'score_evidentiary': evidentiary,
        'rationale': rationale
    })

# Output results as JSON array
output_json = json.dumps(results)

# Write to file
with open(r"C:\Users\Matheus.Ligeiro\Claude Code\final-comparison\claude\scratch\batch_0001_result.json", 'w') as f:
    f.write(output_json)

print(f"Results written to batch_0001_result.json ({len(results)} documents)")
print("\nSample results:")
for i, result in enumerate(results[:3]):
    print(f"\nDoc {i+1}: {result['doc_id'][:16]}...")
    print(f"  Care-first: {result['score_carefirst']}, AI/Tech: {result['score_ai_governance']}, Intersection: {result['score_intersection']}, Evidentiary: {result['score_evidentiary']}")
    print(f"  Rationale: {result['rationale']}")
