import os
import json
import sys
import shutil
from docx import Document

# --- Fonctions utilitaires ---
def extract_text_from_docx(path):
    doc = Document(path)
    content = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            content.append(text)
    return content


def convert_docx_to_json(input_path, output_path):
    content = extract_text_from_docx(input_path)
    data = {"file": os.path.basename(input_path), "paragraphs": content}
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] {input_path} → {output_path}")


def merge_json_files(input_files, output_file):
    merged = {"context_files": []}
    for fpath in input_files:
        with open(fpath, "r", encoding="utf-8") as f:
            merged["context_files"].append(json.load(f))
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"[OK] Contexte global créé : {output_file}")


# --- Programme principal ---
def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)

    context_dir = os.path.join(root_dir, "context")
    json_dir = os.path.join(root_dir, "jsons")
    
    # Vider le contenu du dossier jsons (mais pas le dossier lui-même car c'est un volume monté)
    if os.path.exists(json_dir):
        for filename in os.listdir(json_dir):
            file_path = os.path.join(json_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'⚠️  Erreur lors de la suppression de {file_path}: {e}')
        print(f"🗑️  Contenu du dossier jsons vidé")
    
    # S'assurer que le dossier existe
    os.makedirs(json_dir, exist_ok=True)

    # 1️⃣ Transformer les fichiers du dossier context/
    context_jsons = []
    for fname in os.listdir(context_dir):
        if fname.endswith(".docx"):
            src = os.path.join(context_dir, fname)
            dst = os.path.join(json_dir, f"{os.path.splitext(fname)[0]}.json")
            convert_docx_to_json(src, dst)
            context_jsons.append(dst)

    # Fusionner en un seul JSON global
    context_global_path = os.path.join(json_dir, "context_global.json")
    merge_json_files(context_jsons, context_global_path)

    # 2️⃣ Transformer le fichier principal à la racine
    main_docx = None
    for f in os.listdir(root_dir):
        if f.endswith(".docx"):
            main_docx = os.path.join(root_dir, f)
            break

    if not main_docx:
        print("[ERREUR] Aucun fichier principal .docx trouvé à la racine.")
        sys.exit(1)

    principal_json = os.path.join(json_dir, "principal.json")
    convert_docx_to_json(main_docx, principal_json)

    print(f"\n✅ Conversion terminée.\n- Contexte global : {context_global_path}\n- Principal : {principal_json}")


if __name__ == "__main__":
    main()
