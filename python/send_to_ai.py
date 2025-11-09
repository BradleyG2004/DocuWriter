import os
import re
import json
import requests


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_text(json_data):
    if "paragraphs" in json_data:
        return "\n".join(json_data["paragraphs"])
    elif "context_files" in json_data:
        texts = []
        for ctx in json_data["context_files"]:
            texts.append(extract_text(ctx))
        return "\n".join(texts)
    return ""


def complete_text_with_ai(context_text, document_text, model="llama3.2"):
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    prompt = f"""
You are an assistant whose job is to replace placeholder zones in a document.
You will be given a context (background documents) and a main document that
contains placeholder zones delimited as <here>...</here>. The text inside
<here>...</here> are examples and must be replaced by concrete, adapted
content derived from the context.

Instructions:
- For each placeholder occurrence, provide a replacement text adapted to the
  context. Do NOT include the example text from inside the tags.
- Return a JSON object ONLY (no additional text) with the following structure:
  {{{{
    "replacements": [
      {{{{
        "id": "p{{{{paragraph_index}}}}_h{{{{occurrence_index}}}}",
        "paragraph_index": <int>,
        "original": "<the exact original text inside the <here>...</here>>",
        "replacement": "<the replacement text>"
      }}}}
    ],
    "notes": "optional short note"
  }}}}

Provide concise, useful replacement text (a few sentences or short paragraphs
where appropriate). Each replacement should be self-contained and ready to paste
in place of the <here>...</here> block.

Context:
{{context_text}}

Document to update:
{{document_text}}

Remember: OUTPUT JSON ONLY.
"""

    try:
        response = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=600  # 10 minutes pour un document complexe
        )
    except requests.exceptions.Timeout:
        return {"error": "Timeout: Le modèle a pris trop de temps à répondre. Essayez de réduire la taille du document ou utilisez un modèle plus rapide."}
    except requests.exceptions.RequestException as e:
        return {"error": f"Erreur de connexion: {str(e)}"}

    if response.status_code != 200:
        return {"error": f"{response.status_code} - {response.text}"}

    try:
        res = response.json()
        content = res.get("response") if isinstance(res, dict) else None
        if content is None:
            content = json.dumps(res)
    except Exception:
        content = response.text

    try:
        parsed = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, flags=re.S)
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

    # Identify all <here>...</here> placeholders in the principal document
    paragraphs = principal_data.get("paragraphs", [])
    placeholders = []
    for idx, para in enumerate(paragraphs):
        for occ_idx, match in enumerate(re.finditer(r"<here>(.*?)</here>", para, flags=re.S)):
            original = match.group(1).strip()
            pid = f"p{idx}_h{occ_idx}"
            placeholders.append({
                "id": pid,
                "paragraph_index": idx,
                "occurrence_index": occ_idx,
                "original": original
            })

    print("🔹 Envoi du contexte et du document à l'IA...")
    print(f"   📊 {len(placeholders)} zones <here>...</here> détectées")
    print("   ⏳ Traitement en cours (cela peut prendre plusieurs minutes)...")

    model_response = complete_text_with_ai(context_text, document_text)

    if isinstance(model_response, dict) and model_response.get("error"):
        output_json_path = os.path.join(json_dir, "completed_document.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump({"error": model_response}, f, indent=2, ensure_ascii=False)
        print(f"❌ Erreur lors de l'appel à l'IA: {model_response}")
        return

    parsed = model_response if isinstance(model_response, dict) else {}
    replacements = parsed.get("replacements") if isinstance(parsed, dict) else []
    if not isinstance(replacements, list):
        replacements = []

    # Créer les paires original/remplacement avec balises complètes
    replacement_pairs = []
    applied_paragraphs = list(paragraphs)
    
    for rep in replacements:
        pidx = rep.get("paragraph_index")
        orig = rep.get("original")
        repl = rep.get("replacement")
        if pidx is None or orig is None or repl is None:
            continue
        
        # Construire la paire avec le texte original complet (avec balises)
        original_with_tags = f"<here>{orig}</here>"
        replacement_pairs.append({
            "paragraph_index": pidx,
            "original_text_with_tags": original_with_tags,
            "proposed_replacement": repl
        })
        
        # Appliquer le remplacement
        pattern = re.compile(r"<here>\s*" + re.escape(orig) + r"\s*</here>", flags=re.S)
        try:
            applied_paragraphs[pidx] = pattern.sub(repl, applied_paragraphs[pidx], count=1)
        except Exception:
            continue

    completed_text = "\n".join(applied_paragraphs)

    result_json = {
        "file": principal_data.get("file", "document.docx"),
        "summary": {
            "total_placeholders_found": len(placeholders),
            "total_replacements_applied": len(replacement_pairs)
        },
        "replacement_pairs": replacement_pairs
    }

    output_json_path = os.path.join(json_dir, "completed_document.json")
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    output_txt_path = os.path.join(json_dir, "completed_document.txt")
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(completed_text)

    print(f"✅ Document complété enregistré dans :")
    print(f"   - JSON: {output_json_path}")
    print(f"   - Texte: {output_txt_path}")
    print(f"   📝 {len(replacement_pairs)} remplacements appliqués")


if __name__ == "__main__":
    main()
