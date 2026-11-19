"""Generate a self-contained demonstration workspace."""

from pathlib import Path

from docx import Document


def build_demo_workspace(session_dir: Path) -> tuple[Path, list[Path]]:
    context_dir = session_dir / "context"
    input_dir = session_dir / "tocomplete"
    context_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)

    template = input_dir / "DAT_Template_Cloud.docx"
    document = Document()
    document.add_heading("DAT Cloud Platform", level=1)
    document.add_heading("Architecture", level=2)
    document.add_paragraph("Description: <here>Décrire l'architecture conteneurisée.</here>")
    document.add_heading("Security", level=2)
    document.add_paragraph("Controls: <here>Décrire les contrôles de sécurité.</here>")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Component"
    table.rows[0].cells[1].text = "Protocol"
    row = table.add_row().cells
    row[0].text = "<here>Nom du composant</here>"
    row[1].text = "<here>Protocole utilisé</here>"
    document.save(template)

    specs = context_dir / "specs_infra_aws.docx"
    document = Document()
    document.add_heading("Infrastructure AWS", level=1)
    document.add_paragraph(
        "La plateforme est conteneurisée et déployée sur AWS. Les services "
        "utilisent PostgreSQL pour les données persistantes et un réseau privé."
    )
    document.add_paragraph("Les métriques, logs et traces sont centralisés pour l'observabilité.")
    document.save(specs)

    security = context_dir / "politique_securite.docx"
    document = Document()
    document.add_heading("Politique de sécurité", level=1)
    document.add_paragraph(
        "Les échanges sont chiffrés en TLS. L'authentification des API repose "
        "sur des jetons JWT à durée de vie limitée et une rotation des secrets."
    )
    document.add_paragraph("Les accès PostgreSQL sont restreints et audités.")
    document.save(security)
    return template, [specs, security]
