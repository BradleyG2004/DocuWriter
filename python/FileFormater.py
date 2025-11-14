import os
import json
import sys
import shutil
import re
from docx import Document

# --- Fonctions utilitaires ---
def extract_structured_content_from_docx(path):
    """
    Extrait uniquement les titres (headings) et les contenus avec <here>...</here>
    Retourne une structure hiérarchique avec sections, sous-sections et contenus
    
    Gère les cas où <here> et </here> sont dans des paragraphes différents
    """
    doc = Document(path)
    structure = []
    current_section = None
    current_subsection = None
    current_subsubsection = None
    
    # Variables pour gérer les blocs <here>...</here> multi-paragraphes
    inside_here_block = False
    here_content = []
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        # Déterminer le niveau de titre basé sur le style
        style_name = para.style.name if para.style else ""
        
        # Si on est dans un bloc <here>, accumuler le contenu
        if inside_here_block:
            here_content.append(text)
            # Vérifier si on ferme le bloc
            if '</here>' in text:
                inside_here_block = False
                full_text = '\n'.join(here_content)
                content_item = {
                    "type": "placeholder",
                    "full_text": full_text
                }
                
                # Ajouter au conteneur approprié
                if current_subsubsection and "contents" in current_subsubsection:
                    current_subsubsection["contents"].append(content_item)
                elif current_subsection and "contents" in current_subsection:
                    current_subsection["contents"].append(content_item)
                elif current_section:
                    if "contents" not in current_section:
                        current_section["contents"] = []
                    current_section["contents"].append(content_item)
                else:
                    # Contenu orphelin
                    if not structure or "contents" not in structure[-1]:
                        structure.append({
                            "title": "Contenu sans titre",
                            "level": 0,
                            "contents": []
                        })
                    structure[-1]["contents"].append(content_item)
                
                here_content = []
            continue
        
        # Vérifier si on ouvre un bloc <here>
        if '<here>' in text:
            inside_here_block = True
            here_content = [text]
            # Cas où <here> et </here> sont sur la même ligne
            if '</here>' in text:
                inside_here_block = False
                content_item = {
                    "type": "placeholder",
                    "full_text": text
                }
                
                # Ajouter au conteneur approprié
                if current_subsubsection and "contents" in current_subsubsection:
                    current_subsubsection["contents"].append(content_item)
                elif current_subsection and "contents" in current_subsection:
                    current_subsection["contents"].append(content_item)
                elif current_section:
                    if "contents" not in current_section:
                        current_section["contents"] = []
                    current_section["contents"].append(content_item)
                else:
                    # Contenu orphelin
                    if not structure or "contents" not in structure[-1]:
                        structure.append({
                            "title": "Contenu sans titre",
                            "level": 0,
                            "contents": []
                        })
                    structure[-1]["contents"].append(content_item)
                
                here_content = []
            continue
        
        # Vérifier si c'est un titre de niveau 1
        if style_name.startswith('Heading 1') or style_name == 'Title':
            current_section = {
                "title": text,
                "level": 1,
                "subsections": []
            }
            structure.append(current_section)
            current_subsection = None
            current_subsubsection = None
            
        # Vérifier si c'est un titre de niveau 2
        elif style_name.startswith('Heading 2'):
            if current_section:
                current_subsection = {
                    "title": text,
                    "level": 2,
                    "contents": []
                }
                current_section["subsections"].append(current_subsection)
            else:
                # Si pas de section parente, créer une section
                current_section = {
                    "title": text,
                    "level": 2,
                    "subsections": []
                }
                structure.append(current_section)
                current_subsection = None
            current_subsubsection = None
                
        # Vérifier si c'est un titre de niveau 3+
        elif style_name.startswith('Heading'):
            level = 3
            if 'Heading 3' in style_name:
                level = 3
            elif 'Heading 4' in style_name:
                level = 4
            elif 'Heading 5' in style_name:
                level = 5
                
            sub_item = {
                "title": text,
                "level": level,
                "contents": []
            }
            
            if current_subsection:
                # Ajouter comme sous-sous-section
                if "subsubsections" not in current_subsection:
                    current_subsection["subsubsections"] = []
                current_subsection["subsubsections"].append(sub_item)
                current_subsubsection = sub_item
            elif current_section:
                current_subsection = sub_item
                current_section["subsections"].append(current_subsection)
                current_subsubsection = None
    
    return structure


def extract_text_from_docx(path):
    """Version simple pour les fichiers de contexte"""
    doc = Document(path)
    content = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            content.append(text)
    return content


def extract_text_from_txt(path):
    """Extrait tout le contenu d'un fichier .txt en un seul bloc"""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    return content


def extract_structured_content_from_md(path):
    """Extrait la structure hiérarchique d'un fichier Markdown basé sur les niveaux de #"""
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    structure = []
    current_section = None
    current_subsection = None
    current_subsubsection = None
    
    for line in lines:
        line = line.rstrip()
        
        # Détecter les titres markdown
        if line.startswith('#'):
            # Compter le nombre de #
            level = 0
            for char in line:
                if char == '#':
                    level += 1
                else:
                    break
            
            title = line.lstrip('#').strip()
            
            if level == 1:
                # Titre de niveau 1
                current_section = {
                    "title": title,
                    "level": 1,
                    "subsections": []
                }
                structure.append(current_section)
                current_subsection = None
                current_subsubsection = None
                
            elif level == 2:
                # Titre de niveau 2
                if current_section:
                    current_subsection = {
                        "title": title,
                        "level": 2,
                        "contents": []
                    }
                    current_section["subsections"].append(current_subsection)
                else:
                    current_section = {
                        "title": title,
                        "level": 2,
                        "subsections": []
                    }
                    structure.append(current_section)
                    current_subsection = None
                current_subsubsection = None
                
            else:
                # Titre de niveau 3+
                sub_item = {
                    "title": title,
                    "level": level,
                    "contents": []
                }
                
                if current_subsection:
                    if "subsubsections" not in current_subsection:
                        current_subsection["subsubsections"] = []
                    current_subsection["subsubsections"].append(sub_item)
                    current_subsubsection = sub_item
                elif current_section:
                    current_subsection = sub_item
                    current_section["subsections"].append(current_subsection)
                    current_subsubsection = None
        
        else:
            # Contenu non-titre
            if line.strip():
                # Ajouter le contenu au conteneur approprié
                if current_subsubsection and "contents" in current_subsubsection:
                    if not current_subsubsection["contents"]:
                        current_subsubsection["contents"].append(line)
                    else:
                        current_subsubsection["contents"][-1] += "\n" + line
                elif current_subsection and "contents" in current_subsection:
                    if not current_subsection["contents"]:
                        current_subsection["contents"].append(line)
                    else:
                        current_subsection["contents"][-1] += "\n" + line
                elif current_section:
                    if "contents" not in current_section:
                        current_section["contents"] = []
                    if not current_section["contents"]:
                        current_section["contents"].append(line)
                    else:
                        current_section["contents"][-1] += "\n" + line
    
    return structure


def convert_file_to_json(input_path, output_path, use_structure=False):
    """
    Convertit un fichier (.docx, .txt, .md) en JSON
    
    - .docx: Si use_structure=True, extrait headings et <here>...</here>
             Sinon, extrait tout le texte
    - .txt: Extrait tout le contenu en un seul bloc (pas de structure)
    - .md: Si use_structure=True, extrait la structure selon les niveaux # 
           Sinon, extrait tout le texte
    """
    file_ext = os.path.splitext(input_path)[1].lower()
    
    if file_ext == '.docx':
        if use_structure:
            content = extract_structured_content_from_docx(input_path)
            data = {
                "file": os.path.basename(input_path), 
                "structure": content
            }
        else:
            content = extract_text_from_docx(input_path)
            data = {
                "file": os.path.basename(input_path), 
                "paragraphs": content
            }
    
    elif file_ext == '.txt':
        # Pour .txt, toujours un seul bloc de contenu
        content = extract_text_from_txt(input_path)
        data = {
            "file": os.path.basename(input_path),
            "content": content
        }
    
    elif file_ext == '.md':
        if use_structure:
            content = extract_structured_content_from_md(input_path)
            data = {
                "file": os.path.basename(input_path),
                "structure": content
            }
        else:
            # Version simple : tout le contenu
            content = extract_text_from_txt(input_path)  # Réutilise la fonction txt
            data = {
                "file": os.path.basename(input_path),
                "content": content
            }
    
    else:
        print(f"[WARN] Type de fichier non supporte: {file_ext}")
        return
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] {input_path} -> {output_path}")



def merge_json_files(input_files, output_file):
    merged = {"context_files": []}
    for fpath in input_files:
        with open(fpath, "r", encoding="utf-8") as f:
            merged["context_files"].append(json.load(f))
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"[OK] Contexte global cree : {output_file}")


# --- Programme principal ---
def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)

    context_dir = os.path.join(root_dir, "context")
    json_dir = os.path.join(root_dir, "jsons")
    
    # Vider le contenu du dossier jsons (mais pas le dossier lui-même car c'est un volume monté)
    if os.path.exists(json_dir):
        for filename in os.listdir(json_dir):
            if filename == '.gitkeep':  # Garder le .gitkeep
                continue
            file_path = os.path.join(json_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'[WARN] Erreur lors de la suppression de {file_path}: {e}')
        print("[INFO] Contenu du dossier jsons vide")
    
    # S'assurer que le dossier existe
    os.makedirs(json_dir, exist_ok=True)

    # [1] Transformer les fichiers du dossier context/
    context_jsons = []
    for fname in os.listdir(context_dir):
        # Ignorer les fichiers temporaires et .gitkeep
        if fname == '.gitkeep':
            continue
        if fname.startswith("~$"):  # Fichiers temporaires Word
            continue
        
        # Gérer .docx, .txt, .md
        if fname.endswith((".docx", ".txt", ".md")):
            src = os.path.join(context_dir, fname)
            dst = os.path.join(json_dir, f"{os.path.splitext(fname)[0]}.json")
            
            # Pour les fichiers de contexte, utiliser la structure pour .docx et .md
            use_structure = fname.endswith((".docx", ".md"))
            convert_file_to_json(src, dst, use_structure=use_structure)
            context_jsons.append(dst)

    # Fusionner en un seul JSON global
    context_global_path = os.path.join(json_dir, "context_global.json")
    merge_json_files(context_jsons, context_global_path)

    # [2] Transformer le fichier principal dans tocomplete/ avec structure
    tocomplete_dir = os.path.join(root_dir, "tocomplete")
    main_docx = None
    
    if os.path.exists(tocomplete_dir):
        for f in os.listdir(tocomplete_dir):
            # Ignorer les fichiers temporaires Word et .gitkeep
            if f == '.gitkeep':
                continue
            if f.endswith(".docx") and not f.startswith("~$"):
                main_docx = os.path.join(tocomplete_dir, f)
                break

    if not main_docx:
        print("[ERREUR] Aucun fichier principal .docx trouve dans tocomplete/.")
        sys.exit(1)

    principal_json = os.path.join(json_dir, "principal.json")
    # Utiliser use_structure=True pour extraire uniquement headings et <here>...</here>
    convert_file_to_json(main_docx, principal_json, use_structure=True)

    print(f"\n[OK] Conversion terminee.\n- Contexte global : {context_global_path}\n- Principal : {principal_json}")


if __name__ == "__main__":
    main()
