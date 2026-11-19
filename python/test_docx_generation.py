"""
Script de test pour vérifier la génération du document Word complété
"""
import os
import json
import sys
from docx import Document

# Ajouter le dossier parent au path pour importer send_to_ai
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from send_to_ai import create_completed_docx, create_zip_package

def test_with_sample_data():
    """Test avec le completed_document.json fourni"""
    
    # Chemins
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    
    # Charger le JSON de test (le fichier fourni en attachment)
    test_json_path = os.path.join(root_dir, "Downloads", "completed_document.json")
    
    if not os.path.exists(test_json_path):
        print(f"❌ Fichier de test non trouvé: {test_json_path}")
        print("   Veuillez placer le fichier completed_document.json dans le dossier Downloads")
        return
    
    with open(test_json_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)
    
    print("✅ JSON de test chargé")
    print(f"   Fichier source: {test_data.get('file')}")
    print(f"   Nombre de remplacements: {len(test_data.get('replacement_pairs', []))}")
    
    # Chercher le document original
    tocomplete_dir = os.path.join(root_dir, "tocomplete")
    original_docx = None
    
    if os.path.exists(tocomplete_dir):
        for f in os.listdir(tocomplete_dir):
            if f.endswith(".docx") and not f.startswith("~$"):
                original_docx = os.path.join(tocomplete_dir, f)
                break
    
    if not original_docx:
        print("❌ Aucun document .docx trouvé dans tocomplete/")
        return
    
    print(f"✅ Document original trouvé: {os.path.basename(original_docx)}")
    
    # Créer le document complété
    output_dir = os.path.join(root_dir, "test_output")
    os.makedirs(output_dir, exist_ok=True)
    
    output_docx = os.path.join(output_dir, "test_completed_document.docx")
    
    try:
        replacements_done = create_completed_docx(
            original_docx,
            test_data.get('replacement_pairs', []),
            output_docx
        )
        
        print(f"\n✅ Test réussi !")
        print(f"   Document généré: {output_docx}")
        print(f"   Remplacements effectués: {replacements_done}")
        
        # Créer également un ZIP de test
        test_json_copy = os.path.join(output_dir, "completed_document.json")
        with open(test_json_copy, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2, ensure_ascii=False)
        
        zip_path = os.path.join(output_dir, "test_completion_results.zip")
        create_zip_package(test_json_copy, output_docx, zip_path)
        
        print(f"\n📦 Package ZIP créé: {zip_path}")
        
    except Exception as e:
        print(f"\n❌ Erreur lors du test: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🧪 Test de génération du document Word complété\n")
    test_with_sample_data()
