# DocuWriter

Outil automatisé de complétion de documents techniques basé sur l'IA. DocuWriter utilise Ollama pour générer des propositions de contenu pour les zones à compléter dans vos documents Word.

## 📋 Fonctionnement

Le système extrait les documents Word, identifie les zones à compléter (délimitées par `<here>...</here>`), utilise des documents de contexte pour générer des propositions de remplacement adaptées via IA, et produit un JSON structuré avec toutes les suggestions.

## 🏗️ Architecture

- **Docker Compose** : Orchestration des services (Ollama + Pipeline Python)
- **Ollama** : Serveur d'inférence IA local
- **Python** : 
  - `JsonFormater.py` : Extraction et structuration des documents Word
  - `send_to_ai.py` : Génération des propositions via IA

## 📁 Structure du projet

```
DocuWriter/
├── docker-compose.yml          # Configuration des services
├── context/                    # Documents de référence (.docx)
├── tocomplete/                 # Document principal à compléter (.docx)
├── jsons/                      # Fichiers JSON générés
├── python/
│   ├── Dockerfile
│   ├── JsonFormater.py         # Extraction structurée des documents
│   ├── send_to_ai.py           # Génération IA des propositions
│   └── requirements.txt
└── README.md
```

## 🚀 Utilisation

### 1. Préparation des fichiers

- Placez vos **documents de contexte** (.docx) dans le dossier `context/`
- Placez le **document principal** à compléter (.docx) dans le dossier `tocomplete/`
- Dans le document principal, marquez les zones à compléter avec `<here>...</here>`

### 2. Lancement des conteneurs

```bash
docker-compose up --build
```

Cette commande :
- Démarre le serveur Ollama
- Exécute automatiquement `JsonFormater.py` puis `send_to_ai.py`
- Vide le dossier `jsons/` à chaque exécution
- Extrait la structure hiérarchique (titres + contenus `<here>...</here>`)
- Génère les propositions par lots de 5 zones

### 3. Résultats

Les fichiers générés dans `jsons/` :

- **`context_global.json`** : Fusion de tous les documents de contexte
- **`principal.json`** : Structure hiérarchique du document principal
  ```json
  {
    "file": "nom_du_document.docx",
    "structure": [
      {
        "title": "Titre de section",
        "level": 1,
        "subsections": [
          {
            "title": "Sous-titre",
            "level": 2,
            "contents": [
              {
                "type": "placeholder",
                "full_text": "<here>Texte à remplacer...</here>"
              }
            ]
          }
        ]
      }
    ]
  }
  ```
- **`completed_document.json`** : Propositions de remplacement
  ```json
  {
    "file": "nom_du_document.docx",
    "summary": {
      "total_placeholders_found": 37,
      "total_replacements_proposed": 37,
      "batches_processed": 8
    },
    "replacement_pairs": [
      {
        "section_path": "Introduction/Objet",
        "original_text_with_tags": "<here>...</here>",
        "proposed_replacement": "Texte de remplacement proposé"
      }
    ]
  }
  ```

## ⚙️ Configuration

### Modèle IA

Le modèle par défaut est `llama3.1`. Pour changer :

1. Modifiez dans `python/send_to_ai.py` (ligne ~87) :
   ```python
   def complete_text_with_ai(context_text, placeholders_batch, model="llama3.1"):
   ```

2. Téléchargez le modèle souhaité (exemple) :
   ```bash
   docker exec -it ollama ollama pull mistral
   ```

### Taille des lots

Par défaut, le traitement se fait par lots de **5 placeholders** pour éviter les timeouts.

Pour ajuster (dans `send_to_ai.py`, ligne ~235) :
```python
BATCH_SIZE = 5  # Augmentez ou diminuez selon vos besoins
```

### Timeout

Timeout par lot : **5 minutes** (300 secondes)

Pour modifier (dans `send_to_ai.py`, ligne ~118) :
```python
timeout=300  # en secondes
```

## 🔧 Caractéristiques techniques

### Extraction structurée

`JsonFormater.py` extrait **uniquement** :
- Les **titres** hiérarchiques (Heading 1, 2, 3, etc.)
- Les **contenus** entre balises `<here>...</here>`

**Gestion multi-paragraphes** : Les blocs `<here>...</here>` qui s'étendent sur plusieurs paragraphes Word sont correctement regroupés.

### Traitement par lots

Pour gérer les documents volumineux, `send_to_ai.py` :
- Divise les placeholders en lots de 5
- Traite chaque lot séparément (évite les timeouts)
- Affiche la progression : `Lot 2/8 (5 zones)...`
- Limite le contexte à 5000 caractères par requête

### Nettoyage automatique

À chaque exécution :
- Le dossier `jsons/` est vidé
- Les fichiers temporaires Word (`~$*.docx`) sont ignorés

## 🐛 Dépannage

### Timeout persistant
- Réduisez `BATCH_SIZE` à 3 ou 2
- Utilisez un modèle plus léger (ex: `phi3`, `gemma2:2b`)
- Simplifiez les documents de contexte

### Conteneur tué (exit code 137)
- Manque de mémoire RAM
- Utilisez un modèle plus petit
- Vérifiez les ressources Docker

### Aucune zone détectée
- Vérifiez que les balises sont bien `<here>...</here>`
- Assurez-vous que le document principal est dans le dossier `tocomplete/`
- Vérifiez qu'il n'y a pas de fichiers `~$*.docx` ouverts

## 📝 Notes

- Veuillez à bien installer un LLM sur Ollama avant de debuter .
- Les propositions de l'IA sont **indicatives** et doivent être relues
- Le contexte est limité à 5000 caractères par requête pour optimiser les performances
- Les originaux des documents Word ne sont jamais modifiés
- Seules les zones explicitement marquées `<here>...</here>` sont traitées

## 🔄 Workflow complet

1. Préparez vos documents (contexte + principal avec balises)
2. `docker-compose up --build`
3. Consultez `jsons/completed_document.json`
4. Intégrez manuellement les propositions dans votre document Word
5. Relisez et ajustez le contenu selon vos besoins
