import os
import re
import json
import ollama


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text(json_data):
    """Extrait le texte selon la structure du JSON (paragraphs ou structure)"""
    if "paragraphs" in json_data:
        return "\n".join(json_data["paragraphs"])
    elif "structure" in json_data:
        # Nouvelle structure hiérarchique
        texts = []
        for section in json_data.get("structure", []):
            texts.append(extract_from_section(section))
        return "\n".join(texts)
    elif "context_files" in json_data:
        texts = []
        for ctx in json_data["context_files"]:
            texts.append(extract_text(ctx))
        return "\n".join(texts)
    return ""


def extract_from_section(section):
    """Extrait récursivement le texte d'une section"""
    parts = []
    if "title" in section:
        parts.append(section["title"])
    
    # Contenus directs de la section
    for content in section.get("contents", []):
        if isinstance(content, dict) and content.get("type") == "placeholder":
            parts.append(content.get("full_text", ""))
        elif isinstance(content, str):
            parts.append(content)
    
    # Sous-sections
    for subsection in section.get("subsections", []):
        parts.append(extract_from_section(subsection))
    
    # Sous-sous-sections
    for subsubsection in section.get("subsubsections", []):
        parts.append(extract_from_section(subsubsection))
    
    return "\n".join(parts)


def extract_placeholders_from_section(section, placeholders, path_prefix=""):
    """Extrait récursivement tous les placeholders <here>...</here> d'une section"""
    section_title = section.get("title", "untitled")
    current_path = f"{path_prefix}/{section_title}" if path_prefix else section_title
    
    # Extraire les placeholders des contenus directs
    for idx, content in enumerate(section.get("contents", [])):
        if isinstance(content, dict) and content.get("type") == "placeholder":
            full_text = content.get("full_text", "")
            for occ_idx, match in enumerate(re.finditer(r"<here>(.*?)</here>", full_text, flags=re.S)):
                original = match.group(1).strip()
                pid = f"s{len(placeholders)}_h{occ_idx}"
                placeholders.append({
                    "id": pid,
                    "section_path": current_path,
                    "content_index": idx,
                    "occurrence_index": occ_idx,
                    "original": original,
                    "full_text": full_text
                })
    
    # Traiter les sous-sections
    for subsection in section.get("subsections", []):
        extract_placeholders_from_section(subsection, placeholders, current_path)
    
    # Traiter les sous-sous-sections
    for subsubsection in section.get("subsubsections", []):
        extract_placeholders_from_section(subsubsection, placeholders, current_path)





def complete_text_with_ai(context_text, placeholders_batch, model_name="gemma2:2b"):
    """
    Traite un lot de placeholders à la fois avec Ollama
    """
    # Construire la liste des placeholders pour le prompt
    placeholders_text = ""
    for i, ph in enumerate(placeholders_batch):
        section_path = ph.get("section_path", "N/A")
        original = ph.get("original", "")
        placeholders_text += f"\n[{i+1}] Section: {section_path}\nOriginal: {original[:200]}...\n"

    prompt = f"""You are an assistant whose job is to replace placeholder zones in a document.
You will be given a context (background documents) and a list of placeholder zones
that need to be replaced with concrete, adapted content derived from the context.

Instructions:
- For each placeholder, provide a replacement text adapted to the context
- Return a VALID JSON object ONLY (no comments, no additional text) with this structure:
  {{
    "replacements": [
      {{
        "index": 0,
        "replacement": "the replacement text"
      }}
    ]
  }}

IMPORTANT: 
- Output VALID JSON only (no // comments, no extra text)
- Provide concise, useful replacement text (2-4 sentences)
- Each replacement should be self-contained
- Do NOT use comments like // or /* */ in the JSON
- Use the index number from the list below

Context:
{context_text[:5000]}

Placeholders to replace:
{placeholders_text}

Remember: OUTPUT VALID JSON ONLY, NO COMMENTS.
"""

    try:
        # Appel à Ollama
        response = ollama.chat(
            model=model_name,
            messages=[
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        )
        
        content = response['message']['content'].strip()
        
    except Exception as e:
        return {"error": f"Erreur lors de la generation: {str(e)}"}

    # Parser la réponse JSON
    try:
        parsed = json.loads(content)
    except Exception:
        # Nettoyer le contenu avant de le parser
        content_clean = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)
        content_clean = re.sub(r'/\*.*?\*/', '', content_clean, flags=re.DOTALL)
        
        try:
            parsed = json.loads(content_clean)
        except Exception:
            m = re.search(r"\{.*\}", content_clean, flags=re.S)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    return {"error": "Could not parse model response as JSON", "raw": content}
            else:
                return {"error": "No JSON found in model response", "raw": content}

    return parsed



def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    json_dir = os.path.join(root_dir, "jsons")

    context_json = os.path.join(json_dir, "context_global.json")
    principal_json = os.path.join(json_dir, "principal.json")

    context_data = load_json(context_json)
    principal_data = load_json(principal_json)

    context_text = extract_text(context_data)
    document_text = extract_text(principal_data)

    # Identify all <here>...</here> placeholders
    placeholders = []
    
    # Si c'est une structure hiérarchique
    if "structure" in principal_data:
        for section in principal_data.get("structure", []):
            extract_placeholders_from_section(section, placeholders)
    # Sinon, ancienne méthode avec paragraphs
    elif "paragraphs" in principal_data:
        paragraphs = principal_data.get("paragraphs", [])
        for idx, para in enumerate(paragraphs):
            for occ_idx, match in enumerate(re.finditer(r"<here>(.*?)</here>", para, flags=re.S)):
                original = match.group(1).strip()
                pid = f"p{idx}_h{occ_idx}"
                placeholders.append({
                    "id": pid,
                    "paragraph_index": idx,
                    "occurrence_index": occ_idx,
                    "original": original,
                    "context_path": f"paragraph[{idx}]"
                })

    print("[INFO] Envoi du contexte et du document a l'IA...")
    print(f"   [INFO] {len(placeholders)} zones <here>...</here> detectees")
    
    # Traiter par lots de 5 placeholders à la fois
    BATCH_SIZE = 5
    all_replacement_pairs = []
    total_batches = (len(placeholders) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(placeholders))
        batch = placeholders[start_idx:end_idx]
        
        print(f"   [BATCH {batch_num + 1}/{total_batches}] Traitement de {len(batch)} zones...")
        
        model_response = complete_text_with_ai(context_text, batch)
        
        if isinstance(model_response, dict) and model_response.get("error"):
            print(f"   [WARN] Erreur pour le lot {batch_num + 1}: {model_response.get('error')}")
            continue
        
        parsed = model_response if isinstance(model_response, dict) else {}
        replacements = parsed.get("replacements") if isinstance(parsed, dict) else []
        if not isinstance(replacements, list):
            replacements = []
        
        # Créer les paires pour ce batch
        for rep in replacements:
            rep_index = rep.get("index")
            repl_text = rep.get("replacement")
            
            if rep_index is None or repl_text is None:
                continue
            
            # Récupérer le placeholder correspondant
            if 0 <= rep_index < len(batch):
                ph = batch[rep_index]
                pair = {
                    "original_text_with_tags": f"<here>{ph.get('original', '')}</here>",
                    "proposed_replacement": repl_text
                }
                
                if "section_path" in ph:
                    pair["section_path"] = ph["section_path"]
                    pair["content_index"] = ph.get("content_index")
                elif "paragraph_index" in ph:
                    pair["paragraph_index"] = ph["paragraph_index"]
                
                all_replacement_pairs.append(pair)
        
        print(f"   [OK] Lot {batch_num + 1} traite : {len(replacements)} remplacements generes")

    if not all_replacement_pairs and total_batches > 0:
        error_result = {
            "error": "Aucun remplacement n'a pu etre genere",
            "total_placeholders": len(placeholders),
            "total_batches_attempted": total_batches
        }
        output_json_path = os.path.join(json_dir, "completed_document.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(error_result, f, indent=2, ensure_ascii=False)
        print(f"[ERROR] Aucun remplacement genere")
        return

    result_json = {
        "file": principal_data.get("file", "document.docx"),
        "summary": {
            "total_placeholders_found": len(placeholders),
            "total_replacements_proposed": len(all_replacement_pairs),
            "batches_processed": total_batches
        },
        "replacement_pairs": all_replacement_pairs
    }

    output_json_path = os.path.join(json_dir, "completed_document.json")
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Document complete enregistre dans :")
    print(f"   - JSON: {output_json_path}")
    print(f"   [OK] {len(all_replacement_pairs)}/{len(placeholders)} remplacements proposes")


if __name__ == "__main__":
    main()
