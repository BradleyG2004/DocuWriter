`JsonFormater` flemme de rediger ma doc moi meme

1- Lancement conteneurs , depuis mon terminal : `Docker-compose up --build`
<!-- 2- Telechargement d'une image LLM en local(ici mistral)  , depuis mon terminal : `docker exec -it ollama ollama pull mistral` -->
3- Ensuite , pour chq fichier a considerer pour le contexte : `python JsonFormater.py docs/fichier.docx -o jsons/sortie.json`
4- Une fois apres avoir fait ca ,construisons le contexte : `python context_builder.py`
5- Et en dernier lieu , pour envoyer la requete a OLLAMA: `python send_to_ai.py`  .