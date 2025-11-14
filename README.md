# DocuWriter

Outil automatisé de complétion de documents techniques basé sur l'IA locale. DocuWriter utilise **Ollama** avec le modèle **Gemma** pour générer des propositions de contenu pour les zones à compléter dans vos documents Word.

## 📋 Fonctionnement

Le système extrait vos documents (Word, Markdown, texte), identifie les zones à compléter (délimitées par `<here>...</here>`), utilise des documents de contexte pour générer des propositions de remplacement adaptées via IA locale, et produit un JSON structuré avec toutes les suggestions.

## 🎯 Pour les utilisateurs finaux

### Installation rapide

1. **Installer Ollama** (serveur IA local)
   - Téléchargez et installez depuis : [https://ollama.com/download](https://ollama.com/download)
   - Suivez l'assistant d'installation pour Windows

2. **Télécharger le modèle Gemma**
   - Ouvrez un terminal (PowerShell ou CMD)
   - Exécutez la commande :
     ```bash
     ollama pull gemma2:2b
     ```
   - Patientez quelques minutes pendant le téléchargement (~1.6 GB)

3. **Installer Python** (si pas déjà installé)
   - Python 3.8 ou supérieur requis
   - Téléchargez depuis : [https://www.python.org/downloads/](https://www.python.org/downloads/)

4. **Installer les dépendances Python**
   ```bash
   cd DocuWriter/python
   pip install -r requirements.txt
   ```

### Utilisation de l'interface graphique

1. **Lancer l'application**
   ```bash
   cd DocuWriter/python/GUI
   python home.py
   ```
   Ou double-cliquez sur `home.py` si Python est associé aux fichiers `.py`

2. **Sélectionner les fichiers**
   
   **📚 Fichiers de contexte** :
   - Cliquez sur "Sélectionner des fichiers"
   - Maintenez `Ctrl` pour sélectionner plusieurs fichiers
   - Formats acceptés : `.docx`, `.md`, `.txt`
   - Ces fichiers servent de référence pour générer le contenu

   **📄 Fichier à compléter** :
   - Cliquez sur "Sélectionner un fichier"
   - Format accepté : `.docx` uniquement
   - Ce fichier doit contenir des balises `<here>...</here>` aux endroits à compléter

3. **Lancer le traitement**
   - Cliquez sur "🚀 Générer les propositions"
   - Une fenêtre de progression s'affiche avec un loader animé
   - Patientez pendant le traitement (quelques minutes selon la taille)

4. **Télécharger le résultat**
   - Une fois terminé, une fenêtre s'ouvre automatiquement
   - Cliquez sur "📥 Télécharger le JSON"
   - Enregistrez le fichier `completed_document.json`

### Exemple de balise dans votre document

Dans votre fichier Word à compléter, insérez :
```
<here>
Décrivez brièvement ce que vous voulez voir généré ici,
ou laissez vide pour une génération contextuelle automatique.
</here>
```

## 🏗️ Architecture

- **Ollama** : Serveur d'inférence IA local avec modèle Gemma
- **Python** : 
  - **`home.py`** : Interface graphique pour la sélection de fichiers
  - **`FileFormater.py`** : Extraction et structuration des documents
  - **`send_to_ai.py`** : Génération des propositions via Ollama

## 📁 Structure du projet

```
DocuWriter/
├── context/                    # Documents de référence (.docx, .md, .txt)
├── tocomplete/                 # Document principal à compléter (.docx)
├── jsons/                      # Fichiers JSON générés
├── python/
│   ├── GUI/
│   │   └── home.py            # Interface graphique
│   ├── FileFormater.py        # Extraction structurée des documents
│   ├── send_to_ai.py          # Génération IA des propositions
│   └── requirements.txt
└── README.md
```
## ⚙️ Configuration

### Formats de fichiers supportés

**Fichiers de contexte** :
- `.docx` : Structure hiérarchique extraite (titres H1, H2, H3, etc.)
- `.md` : Structure hiérarchique selon les niveaux `#`, `##`, `###`, etc.
- `.txt` : Contenu brut en un seul bloc

**Fichier à compléter** :
- `.docx` uniquement (avec balises `<here>...</here>`)

### Modèle IA

Le modèle par défaut est **`gemma2:2b`** (léger et rapide).

Pour changer de modèle :

1. Téléchargez un autre modèle Ollama :
   ```bash
   ollama pull llama3.1
   # ou
   ollama pull mistral
   ```

2. Modifiez dans `python/send_to_ai.py` (ligne ~94) :
   ```python
   def complete_text_with_ai(context_text, placeholders_batch, model_name="llama3.1"):
   ```

### Taille des lots

Par défaut, le traitement se fait par lots de **5 placeholders** pour optimiser les performances.

Pour ajuster (dans `send_to_ai.py`, ligne ~235) :
```python
BATCH_SIZE = 5  # Augmentez ou diminuez selon vos besoins
```

## 🔧 Caractéristiques techniques

### Extraction structurée

`FileFormater.py` extrait selon le type de fichier :

**Documents Word (.docx)** :
- **Titres** hiérarchiques (Heading 1, 2, 3, etc.)
- **Contenus** entre balises `<here>...</here>`
- Gestion des blocs multi-paragraphes

**Markdown (.md)** :
- Structure selon les niveaux `#`, `##`, `###`
- Contenu par section

**Texte (.txt)** :
- Contenu brut en un seul bloc

### Traitement par lots

Pour gérer les documents volumineux, `send_to_ai.py` :
- Divise les placeholders en lots de 5
- Traite chaque lot séparément via Ollama
- Affiche la progression : `[BATCH 2/8] Traitement de 5 zones...`
- Limite le contexte à 5000 caractères par requête

### Interface graphique

L'interface `home.py` offre :
- ✅ Sélection multi-fichiers (Ctrl + Click)
- ✅ Validation des formats
- ✅ Fenêtre de progression avec loader animé
- ✅ Mises à jour en temps réel du statut
- ✅ Téléchargement du JSON résultat

## 🐛 Dépannage

### Ollama ne répond pas
- Vérifiez qu'Ollama est démarré : ouvrez l'application Ollama
- Testez avec : `ollama list` pour voir les modèles installés
- Redémarrez Ollama si nécessaire

### Erreur "Import ollama could not be resolved"
```bash
pip install ollama
```

### Le traitement est trop lent
- Utilisez `gemma2:2b` (modèle le plus léger et rapide)
- Réduisez `BATCH_SIZE` à 3
- Simplifiez les documents de contexte

### Aucune zone détectée
- Vérifiez que les balises sont bien `<here>...</here>` (en minuscules)
- Assurez-vous que le document principal est au bon format (.docx)
- Fermez le fichier Word avant de lancer le traitement

### L'interface ne se lance pas
```bash
pip install customtkinter python-docx ollama
```

## 📝 Notes

- Les propositions de l'IA sont **indicatives** et doivent être relues
- Le contexte est limité à 5000 caractères par requête pour optimiser les performances
- Les originaux des documents ne sont jamais modifiés
- Seules les zones explicitement marquées `<here>...</here>` sont traitées
- Ollama fonctionne **100% en local**, aucune donnée n'est envoyée sur internet

## 🔄 Workflow complet

### Via l'interface graphique (recommandé)

1. **Installation** : Ollama + Gemma + dépendances Python
2. **Lancer** : `python home.py`
3. **Sélectionner** : Fichiers de contexte + fichier à compléter
4. **Générer** : Cliquez sur le bouton, patientez pendant le loader
5. **Télécharger** : Enregistrez le JSON avec les propositions
6. **Intégrer** : Copiez manuellement les propositions dans votre document
7. **Relire** : Ajustez et validez le contenu

### Via ligne de commande

1. Placez vos fichiers dans `context/` et `tocomplete/`
2. `python FileFormater.py` → Extraction JSON
3. `python send_to_ai.py` → Génération propositions
4. Consultez `jsons/completed_document.json`
5. Intégrez et relisez

## 🌐 Liens utiles

- **Ollama** : [https://ollama.com/download](https://ollama.com/download)
- **Modèles disponibles** : [https://ollama.com/library](https://ollama.com/library)
- **Gemma** : [https://ollama.com/library/gemma2](https://ollama.com/library/gemma2)
- **Python** : [https://www.python.org/downloads/](https://www.python.org/downloads/)