# Configuration de DocuWriter avec llama-cpp-python

## Installation

### 1. Installer les dépendances Python

```powershell
cd DocuWriter
pip install -r python/requirements.txt
```

**Note**: L'installation de `llama-cpp-python` peut prendre quelques minutes car elle compile des binaires C++.

### 2. Télécharger un modèle LLM

Vous devez télécharger un modèle au format GGUF. Voici quelques options :

#### Option A : Modèles recommandés (légers et performants)

1. **Phi-3 Mini (3.8B)** - Excellent rapport qualité/taille
   - Lien : https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf
   - Fichier : `Phi-3-mini-4k-instruct-q4.gguf` (~2.3 GB)

2. **Llama 3.2 (3B)** - Très performant
   - Lien : https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF
   - Fichier : `Llama-3.2-3B-Instruct-Q4_K_M.gguf` (~1.9 GB)

3. **Mistral 7B** - Plus puissant mais plus lourd
   - Lien : https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF
   - Fichier : `mistral-7b-instruct-v0.2.Q4_K_M.gguf` (~4.4 GB)

#### Option B : Téléchargement automatique avec huggingface-hub

```powershell
pip install huggingface-hub
```

```python
# Script Python pour télécharger un modèle
from huggingface_hub import hf_hub_download

# Télécharger Phi-3 Mini
model_path = hf_hub_download(
    repo_id="microsoft/Phi-3-mini-4k-instruct-gguf",
    filename="Phi-3-mini-4k-instruct-q4.gguf",
    local_dir="./models"
)
print(f"Modèle téléchargé : {model_path}")
```

### 3. Placer le modèle

Créez un dossier `models` à la racine du projet et placez-y le fichier `.gguf` :

```
DocuWriter/
├── models/
│   └── model.gguf  (renommez votre fichier téléchargé)
├── python/
├── context/
└── ...
```

**Ou** spécifiez le chemin dans `send_to_ai.py` :

```python
# Dans main(), modifiez cette ligne :
model_response = complete_text_with_ai(
    context_text, 
    batch, 
    model_path="C:/chemin/vers/votre/modele.gguf"
)
```

## Utilisation

### Lancer l'application

```powershell
py python/GUI/home.py
```

### Workflow

1. Sélectionnez vos fichiers de contexte (.docx, .md, .txt)
2. Sélectionnez le fichier à compléter (.docx avec `<here>...</here>`)
3. Cliquez sur "Générer les propositions"
4. Attendez le traitement (peut prendre plusieurs minutes selon le modèle)
5. Téléchargez le JSON avec les propositions

## Performances

| Modèle | Taille | RAM requise | Vitesse | Qualité |
|--------|--------|-------------|---------|---------|
| Phi-3 Mini 4K | 2.3 GB | 4-6 GB | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| Llama 3.2 3B | 1.9 GB | 4-6 GB | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ |
| Mistral 7B | 4.4 GB | 8-10 GB | ⚡⚡ | ⭐⭐⭐⭐⭐ |

## Résolution de problèmes

### Erreur "Modele non trouve"

Vérifiez que le fichier `models/model.gguf` existe ou spécifiez le bon chemin.

### Erreur de mémoire

Essayez un modèle plus petit (Phi-3 Mini ou Llama 3.2 3B).

### Génération trop lente

- Réduisez `n_ctx` dans `send_to_ai.py` (ligne avec `n_ctx=4096`)
- Augmentez `n_threads` pour utiliser plus de cœurs CPU
- Utilisez un modèle quantifié Q4 ou Q5 (pas Q8)

### Format JSON invalide

Le modèle peut parfois générer du texte avant/après le JSON. Le script essaie de nettoyer automatiquement, mais vous pouvez ajuster le prompt dans `complete_text_with_ai()`.

## Avantages vs Docker/Ollama

✅ Pas besoin de Docker  
✅ Plus rapide à démarrer  
✅ Contrôle total sur le modèle  
✅ Fonctionne offline  
✅ Moins de dépendances  

❌ Nécessite téléchargement manuel du modèle  
❌ Consomme plus de RAM pendant l'exécution  
