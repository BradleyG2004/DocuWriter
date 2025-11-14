import customtkinter
from tkinter import filedialog
import os
import webbrowser
import shutil
import subprocess
import threading

class DocuWriterApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        
        # Configuration de la fenêtre
        self.title("DocuWriter")
        self.geometry("700x530")
        self.grid_columnconfigure(0, weight=1)
        
        # Couleurs personnalisées
        self.configure(fg_color="white")
        
        # Variables pour stocker les fichiers
        self.context_files = []
        self.file_to_complete = None
        
        # En-tête
        self.header = customtkinter.CTkLabel(
            self,
            text="📝 DocuWriter",
            font=customtkinter.CTkFont(size=24, weight="bold"),
            text_color="black"
        )
        self.header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.subtitle = customtkinter.CTkLabel(
            self,
            text="Complétez vos documents avec l'IA",
            font=customtkinter.CTkFont(size=12),
            text_color="#555555"
        )
        self.subtitle.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        
        # Frame pour les fichiers de contexte
        self.context_frame = customtkinter.CTkFrame(self, fg_color="#f8f9fa", border_width=1, border_color="#e0e0e0")
        self.context_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.context_frame.grid_columnconfigure(1, weight=1)
        
        self.context_label = customtkinter.CTkLabel(
            self.context_frame,
            text="📚 Fichiers de contexte :",
            font=customtkinter.CTkFont(size=14, weight="bold"),
            text_color="black"
        )
        self.context_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w", columnspan=2)

        self.context_info = customtkinter.CTkLabel(
            self.context_frame,
            text="Astuce : Ctrl + Click pour sélectionner plusieurs fichiers (.docx, .md, .txt)",
            font=customtkinter.CTkFont(size=10),
            text_color="#666666"
        )
        
        self.context_info.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w", columnspan=2)
        
        self.context_button = customtkinter.CTkButton(
            self.context_frame,
            text="Sélectionner des fichiers",
            command=self.select_context_files,
            width=200,
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="white",
            border_width=0,
            corner_radius=3
        )
        self.context_button.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        
        self.context_count_label = customtkinter.CTkLabel(
            self.context_frame,
            text="Aucun fichier sélectionné",
            font=customtkinter.CTkFont(size=11),
            text_color="#666666"
        )
        self.context_count_label.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # Frame pour le fichier à compléter
        self.complete_frame = customtkinter.CTkFrame(self, fg_color="#f8f9fa", border_width=1, border_color="#e0e0e0")
        self.complete_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.complete_frame.grid_columnconfigure(1, weight=1)
        
        self.complete_label = customtkinter.CTkLabel(
            self.complete_frame,
            text="📄 Fichier à compléter:",
            font=customtkinter.CTkFont(size=14, weight="bold"),
            text_color="black"
        )
        self.complete_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w", columnspan=2)
        
        self.complete_info = customtkinter.CTkLabel(
            self.complete_frame,
            text="Format accepté: .docx uniquement",
            font=customtkinter.CTkFont(size=10),
            text_color="#666666"
        )
        self.complete_info.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w", columnspan=2)
        
        self.complete_button = customtkinter.CTkButton(
            self.complete_frame,
            text="Sélectionner un fichier",
            command=self.select_file_to_complete,
            width=200,
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="white",
            border_width=0,
            corner_radius=3
        )
        self.complete_button.grid(row=2, column=0, padx=10, pady=10, sticky="w")
        
        self.complete_file_label = customtkinter.CTkLabel(
            self.complete_frame,
            text="Aucun fichier sélectionné",
            font=customtkinter.CTkFont(size=11),
            text_color="#666666"
        )
        self.complete_file_label.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        
        # Bouton de traitement
        self.process_button = customtkinter.CTkButton(
            self,
            text="🚀 Générer les propositions",
            command=self.process_documents,
            height=40,
            font=customtkinter.CTkFont(size=14, weight="bold"),
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="white",
            border_width=0,
            corner_radius=3,
            state="abled"
        )
        self.process_button.grid(row=4, column=0, padx=20, pady=20, sticky="ew")
        
        # Footer avec logo Ollama
        self.footer_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.footer_frame.grid(row=5, column=0, padx=20, pady=(10, 20), sticky="ew")
        self.footer_frame.grid_columnconfigure(0, weight=1)
        
        self.ollama_label = customtkinter.CTkLabel(
            self.footer_frame,
            text="🤖 Utilise Ollama",
            font=customtkinter.CTkFont(size=10, underline=True),
            text_color="#3498db",
            cursor="hand2"
        )
        self.ollama_label.grid(row=0, column=1, padx=10, sticky="e")
        self.ollama_label.bind("<Button-1>", lambda e: webbrowser.open("https://www.datacamp.com/tutorial/docker-ollama-run-llms-locally"))
    
    def select_context_files(self):
        """Sélectionner plusieurs fichiers de contexte """
        files = filedialog.askopenfilenames(
            title="Sélectionner les fichiers de contexte",
            filetypes=[
                ("Fichiers documents", "*.docx *.md *.txt"),
                ("Word Documents", "*.docx"),
                ("Markdown", "*.md"),
                ("Text Files", "*.txt")
            ]
        )
        
        if files:
            self.context_files = list(files)
            count = len(self.context_files)
            self.context_count_label.configure(
                text=f"✅ {count} fichier{'s' if count > 1 else ''} sélectionné{'s' if count > 1 else ''}",
                text_color="#2ecc71"
            )
            self.check_ready_to_process()
    
    def select_file_to_complete(self):
        """Sélectionner le fichier à compléter"""
        file = filedialog.askopenfilename(
            title="Sélectionner le fichier à compléter",
            filetypes=[
                ("Word Documents", "*.docx")
            ]
        )
        
        if file:
            if not file.endswith('.docx'):
                self.complete_file_label.configure(
                    text="❌ Seuls les fichiers .docx sont acceptés",
                    text_color="#e74c3c"
                )
                self.file_to_complete = None
            else:
                self.file_to_complete = file
                filename = os.path.basename(file)
                self.complete_file_label.configure(
                    text=f"✅ {filename}",
                    text_color="#2ecc71"
                )
            self.check_ready_to_process()
    
    def check_ready_to_process(self):
        """Vérifier si tous les fichiers sont sélectionnés"""
        print(f"🔍 Vérification: context_files={len(self.context_files)}, file_to_complete={'✅' if self.file_to_complete else '❌'}")
        
        if self.context_files and self.file_to_complete:
            print("✅ Tous les fichiers sont sélectionnés - Activation du bouton")
            self.process_button.configure(state="normal")
        else:
            print("⚠️ Fichiers manquants - Bouton désactivé")
            self.process_button.configure(state="disabled")
    
    def validate_files(self):
        """Valider tous les fichiers avant le traitement"""
        errors = []
        
        # Vérifier que les champs ne sont pas vides
        if not self.context_files:
            errors.append("❌ Aucun fichier de contexte sélectionné")
        
        if not self.file_to_complete:
            errors.append("❌ Aucun fichier à compléter sélectionné")
        
        # Valider les fichiers de contexte
        if self.context_files:
            valid_context_extensions = ['.docx', '.md', '.txt']
            for file in self.context_files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in valid_context_extensions:
                    errors.append(f"❌ Fichier de contexte invalide: {os.path.basename(file)} (types acceptés: .docx, .md, .txt)")
        
        # Valider le fichier à compléter
        if self.file_to_complete:
            if not self.file_to_complete.lower().endswith('.docx'):
                errors.append(f"❌ Fichier à compléter invalide: {os.path.basename(self.file_to_complete)} (seul .docx est accepté)")
        
        return errors
    
    def show_error_dialog(self, errors):
        """Afficher une boîte de dialogue avec les erreurs"""
        error_window = customtkinter.CTkToplevel(self)
        error_window.title("Validation des fichiers")
        error_window.geometry("300x200")
        error_window.configure(fg_color="white")
        
        # Rendre la fenêtre modale
        error_window.transient(self)
        error_window.grab_set()
        
        # Titre
        title_label = customtkinter.CTkLabel(
            error_window,
            text="❌ Erreurs de validation",
            font=customtkinter.CTkFont(size=18, weight="bold"),
            text_color="#e74c3c"
        )
        title_label.pack(padx=20, pady=(20, 10))
        
        # Frame pour la liste d'erreurs avec scrollbar
        error_frame = customtkinter.CTkScrollableFrame(
            error_window,
            fg_color="#f8f9fa",
            border_width=1,
            border_color="#e0e0e0"
        )
        error_frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Afficher chaque erreur
        for error in errors:
            error_label = customtkinter.CTkLabel(
                error_frame,
                text=error,
                font=customtkinter.CTkFont(size=11),
                text_color="#333333",
                anchor="w",
                justify="left"
            )
            error_label.pack(padx=10, pady=5, anchor="w", fill="x")
        
        # Bouton de fermeture
        close_button = customtkinter.CTkButton(
            error_window,
            text="Fermer",
            command=error_window.destroy,
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="white",
            corner_radius=3
        )
        close_button.pack(padx=20, pady=(10, 20))
    
    def show_download_dialog(self, json_path):
        """Afficher une boîte de dialogue pour télécharger le JSON"""
        download_window = customtkinter.CTkToplevel(self)
        download_window.title("✅ Traitement terminé")
        download_window.geometry("450x250")
        download_window.configure(fg_color="white")
        
        # Rendre la fenêtre modale
        download_window.transient(self)
        download_window.grab_set()
        
        # Titre
        title_label = customtkinter.CTkLabel(
            download_window,
            text="✅ Propositions générées !",
            font=customtkinter.CTkFont(size=18, weight="bold"),
            text_color="#2ecc71"
        )
        title_label.pack(padx=20, pady=(20, 10))
        
        # Message
        info_label = customtkinter.CTkLabel(
            download_window,
            text="Les propositions de complétion ont été générées avec succès.\nVous pouvez maintenant télécharger le fichier JSON.",
            font=customtkinter.CTkFont(size=12),
            text_color="#333333",
            justify="center"
        )
        info_label.pack(padx=20, pady=10)
        
        # Bouton de téléchargement
        def download_json():
            save_path = filedialog.asksaveasfilename(
                title="Enregistrer le fichier JSON",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile="completed_document.json"
            )
            if save_path:
                try:
                    shutil.copy2(json_path, save_path)
                    print(f"✅ Fichier téléchargé: {save_path}")
                    download_window.destroy()
                except Exception as e:
                    print(f"❌ Erreur lors du téléchargement: {str(e)}")
        
        download_button = customtkinter.CTkButton(
            download_window,
            text="📥 Télécharger le JSON",
            command=download_json,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            text_color="white",
            corner_radius=3,
            height=40,
            font=customtkinter.CTkFont(size=13, weight="bold")
        )
        download_button.pack(padx=20, pady=(10, 5))
        
        # Bouton fermer
        close_button = customtkinter.CTkButton(
            download_window,
            text="Fermer",
            command=download_window.destroy,
            fg_color="#1a1a1a",
            hover_color="#333333",
            text_color="white",
            corner_radius=3
        )
        close_button.pack(padx=20, pady=(5, 20))
    
    def process_documents(self):
        """Traiter les documents sélectionnés"""
        print("🔘 Bouton cliqué - Début du traitement")
        
        # Valider tous les fichiers
        errors = self.validate_files()
        
        print(f"📋 Validation terminée - {len(errors)} erreur(s) trouvée(s)")
        
        if errors:
            print("⚠️ Affichage de la boîte de dialogue d'erreur")
            self.show_error_dialog(errors)
            return
        
        # Si tout est valide, continuer le traitement
        print("✅ Validation réussie - Début du traitement")
        print("=== Traitement des documents ===")
        print(f"Fichiers de contexte ({len(self.context_files)}):")
        for f in self.context_files:
            print(f"  - {f}")
        print(f"\nFichier à compléter:")
        print(f"  - {self.file_to_complete}")
        print("\n🚀 Lancement du traitement...")
        
        # Créer la fenêtre de progression
        self.progress_window = customtkinter.CTkToplevel(self)
        self.progress_window.title("⏳ Traitement en cours")
        self.progress_window.geometry("450x280")
        self.progress_window.configure(fg_color="white")
        self.progress_window.transient(self)
        self.progress_window.grab_set()
        
        # Empêcher la fermeture de la fenêtre
        self.progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
        
        # Titre
        title_label = customtkinter.CTkLabel(
            self.progress_window,
            text="⏳ Traitement en cours",
            font=customtkinter.CTkFont(size=18, weight="bold"),
            text_color="#3498db"
        )
        title_label.pack(padx=20, pady=(20, 10))
        
        # Label de statut
        self.progress_status_label = customtkinter.CTkLabel(
            self.progress_window,
            text="Validation des fichiers...",
            font=customtkinter.CTkFont(size=12),
            text_color="#333333"
        )
        self.progress_status_label.pack(padx=20, pady=10)
        
        # Barre de progression indéterminée (loader)
        self.progress_bar = customtkinter.CTkProgressBar(
            self.progress_window,
            mode="indeterminate",
            width=380,
            height=8,
            progress_color="#3498db"
        )
        self.progress_bar.pack(padx=20, pady=10)
        self.progress_bar.start()
        
        # Frame pour les détails
        details_frame = customtkinter.CTkFrame(
            self.progress_window,
            fg_color="#f8f9fa",
            border_width=1,
            border_color="#e0e0e0"
        )
        details_frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Label de détails
        self.progress_details_label = customtkinter.CTkLabel(
            details_frame,
            text="Préparation...",
            font=customtkinter.CTkFont(size=10),
            text_color="#666666",
            anchor="w",
            justify="left"
        )
        self.progress_details_label.pack(padx=15, pady=15, fill="both", expand=True)
        
        # Lancer le traitement réel dans un thread séparé
        threading.Thread(target=self.execute_processing, daemon=True).start()
    
    def update_progress(self, status, details=""):
        """Mettre à jour le statut de progression dans l'interface"""
        def update_ui():
            if hasattr(self, 'progress_status_label') and self.progress_status_label.winfo_exists():
                self.progress_status_label.configure(text=status)
            if hasattr(self, 'progress_details_label') and details and self.progress_details_label.winfo_exists():
                self.progress_details_label.configure(text=details)
        
        # Exécuter dans le thread principal
        self.after(0, update_ui)
    
    def close_progress_window(self):
        """Fermer la fenêtre de progression"""
        def close_ui():
            if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
                try:
                    self.progress_bar.stop()
                    self.progress_window.destroy()
                except:
                    pass
        
        # Exécuter dans le thread principal
        self.after(0, close_ui)
    
    def execute_processing(self):
        """Exécuter le traitement des fichiers"""
        try:
            # Obtenir le chemin du projet
            # home.py est dans python/GUI/, donc on remonte de 2 niveaux
            current_file = os.path.abspath(__file__)  # .../python/GUI/home.py
            gui_dir = os.path.dirname(current_file)    # .../python/GUI
            python_dir = os.path.dirname(gui_dir)      # .../python
            project_root = os.path.dirname(python_dir) # .../DocuWriter
            
            context_dir = os.path.join(project_root, "context")
            tocomplete_dir = os.path.join(project_root, "tocomplete")
            
            print(f"📁 Projet racine: {project_root}")
            print(f"📁 Dossier context: {context_dir}")
            print(f"📁 Dossier tocomplete: {tocomplete_dir}")
            
            # 1. Vider et copier les fichiers de contexte
            self.update_progress("📚 Copie des fichiers de contexte...", f"Copie de {len(self.context_files)} fichier(s)...")
            print("\n📚 Copie des fichiers de contexte...")
            print(f"  📊 Nombre de fichiers: {len(self.context_files)}")
            
            # Vider le dossier context
            if os.path.exists(context_dir):
                for filename in os.listdir(context_dir):
                    if filename != '.gitkeep':  # Garder le .gitkeep
                        file_path = os.path.join(context_dir, filename)
                        try:
                            if os.path.isfile(file_path):
                                os.unlink(file_path)
                        except Exception as e:
                            print(f"⚠️ Erreur lors de la suppression de {file_path}: {e}")
            else:
                # Créer le dossier s'il n'existe pas
                os.makedirs(context_dir, exist_ok=True)
                print(f"  📁 Dossier context créé: {context_dir}")
            
            # Copier les nouveaux fichiers de contexte
            for i, file in enumerate(self.context_files, 1):
                if not os.path.exists(file):
                    print(f"  ⚠️ Fichier introuvable (ignoré): {file}")
                    continue
                dest = os.path.join(context_dir, os.path.basename(file))
                shutil.copy2(file, dest)
                print(f"  ✅ Copié: {os.path.basename(file)}")
                self.update_progress("📚 Copie des fichiers de contexte...", f"Fichier {i}/{len(self.context_files)}: {os.path.basename(file)}")
            
            # 2. Vider et copier le fichier à compléter
            self.update_progress("📄 Copie du fichier à compléter...", f"Copie de {os.path.basename(self.file_to_complete)}...")
            print("\n📄 Copie du fichier à compléter...")
            print(f"  📍 Fichier source: {self.file_to_complete}")
            print(f"  📍 Fichier existe: {os.path.exists(self.file_to_complete) if self.file_to_complete else 'None'}")
            
            # Vérification de sécurité
            if not self.file_to_complete:
                raise ValueError("Aucun fichier à compléter sélectionné")
            
            if not os.path.exists(self.file_to_complete):
                raise FileNotFoundError(f"Le fichier n'existe pas: {self.file_to_complete}")
            
            # Vider le dossier tocomplete
            if os.path.exists(tocomplete_dir):
                for filename in os.listdir(tocomplete_dir):
                    if filename != '.gitkeep':  # Garder le .gitkeep
                        file_path = os.path.join(tocomplete_dir, filename)
                        try:
                            if os.path.isfile(file_path):
                                os.unlink(file_path)
                        except Exception as e:
                            print(f"⚠️ Erreur lors de la suppression de {file_path}: {e}")
            else:
                # Créer le dossier s'il n'existe pas
                os.makedirs(tocomplete_dir, exist_ok=True)
                print(f"  📁 Dossier tocomplete créé: {tocomplete_dir}")
            
            # Copier le fichier à compléter
            dest = os.path.join(tocomplete_dir, os.path.basename(self.file_to_complete))
            print(f"  📍 Destination: {dest}")
            shutil.copy2(self.file_to_complete, dest)
            print(f"  ✅ Copié: {os.path.basename(self.file_to_complete)}")
            
            # 3. Exécuter FileFormater.py
            self.update_progress("🔄 Extraction de la structure du document...", "Analyse des titres et placeholders...")
            print("\n🚀 Exécution de FileFormater.py...")
            Fileformater_path = os.path.join(project_root, "python", "FileFormater.py")
            
            # Exécuter le script Python
            result = subprocess.run(
                ["py", Fileformater_path],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            
            print("📤 Sortie de FileFormater.py:")
            print(result.stdout)
            
            if result.stderr:
                print("⚠️ Erreurs:")
                print(result.stderr)
            
            if result.returncode == 0:
                print("\n✅ Traitement terminé avec succès!")
                
                # 4. Exécuter send_to_ai.py
                self.update_progress("🤖 Génération des propositions avec l'IA...", "Cela peut prendre quelques instants...")
                print("\n🚀 Exécution de send_to_ai.py...")
                send_to_ai_path = os.path.join(project_root, "python", "send_to_ai.py")
                
                # Exécuter le script Python
                result_ai = subprocess.run(
                    ["py", send_to_ai_path],
                    cwd=project_root,
                    capture_output=True,
                    text=True
                )
                
                print("📤 Sortie de send_to_ai.py:")
                print(result_ai.stdout)
                
                if result_ai.stderr:
                    print("⚠️ Erreurs:")
                    print(result_ai.stderr)
                
                if result_ai.returncode == 0:
                    print("\n✅ Génération des propositions terminée avec succès!")
                    
                    # Fermer la fenêtre de progression
                    self.close_progress_window()
                    
                    # 5. Proposer de télécharger le fichier JSON généré
                    json_output_path = os.path.join(project_root, "jsons", "completed_document.json")
                    if os.path.exists(json_output_path):
                        # Afficher le dialogue dans le thread principal
                        self.after(100, lambda: self.show_download_dialog(json_output_path))
                    else:
                        print("⚠️ Fichier JSON non trouvé")
                else:
                    self.close_progress_window()
                    print(f"\n❌ Erreur lors de l'exécution de send_to_ai.py (code: {result_ai.returncode})")
            else:
                self.close_progress_window()
                print(f"\n❌ Erreur lors de l'exécution (code: {result.returncode})")
            
        except Exception as e:
            self.close_progress_window()
            print(f"\n❌ Erreur lors du traitement: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    customtkinter.set_appearance_mode("light")
    customtkinter.set_default_color_theme("blue")
    
    app = DocuWriterApp()
    app.mainloop()