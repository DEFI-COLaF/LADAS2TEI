from __future__ import annotations

from pathlib import Path

import click
from lxml import etree as ET

from ladas2tei.alto import document_subdirectories, expand_alto_inputs
from ladas2tei.metadata import load_metadata, select_metadata
from ladas2tei.models import TeiConversion
from ladas2tei.tei import build_tei, write_tei
from ladas2tei.validation import (
    resolve_tei_rng_path,
    validate_tei_files,
    validation_report_path,
    write_rng_report,
)


@click.command()
@click.argument("alto_files", nargs=-1, type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Fichier TEI ou dossier de sortie.")
@click.option("--metadata-csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--title", type=str, help="Titre TEI a utiliser dans l'en-tete.")
@click.option("--article", is_flag=True, help='Ajoute un div type="article" autour du contenu.')
@click.option("--theatre", is_flag=True, help="Traite les locuteurs et les vers comme une piece de theatre.")
@click.option(
    "--tei-rng",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Schema RNG TEI global a utiliser pour valider les fichiers produits.",
)
def main(
    alto_files: tuple[Path, ...],
    output: Path | None,
    metadata_csv: Path | None,
    title: str | None,
    article: bool,
    theatre: bool,
    tei_rng: Path | None,
) -> None:
    """Lance la conversion depuis la ligne de commande.

    :param alto_files: fichiers ALTO ou dossiers a convertir.
    :type alto_files: tuple[Path, ...]
    :param output: fichier XML ou dossier de sortie.
    :type output: Path | None
    :param metadata_csv: CSV de metadonnees, si fourni.
    :type metadata_csv: Path | None
    :param title: titre force dans l'en-tete TEI.
    :type title: str | None
    :param article: active le wrapper div type="article".
    :type article: bool
    :param theatre: active le traitement des pieces de theatre.
    :type theatre: bool
    :param tei_rng: schema RNG TEI global.
    :type tei_rng: Path | None

    :return: None; ecrit le TEI ou l'affiche dans le terminal.
    :rtype: None
    """
    if not alto_files:
        raise click.UsageError("Donne au moins un fichier ou dossier ALTO XML en entree.")

    # On lit les metadonnees une seule fois, puis on choisit le mode de conversion.
    metadata_rows = load_metadata(metadata_csv)
    if is_batch_directory(alto_files):
        if title:
            raise click.UsageError("--title ne peut pas etre utilise avec un dossier parent.")
        if not metadata_csv:
            raise click.UsageError("--metadata-csv est obligatoire avec un dossier parent.")
        convert_parent_directory(alto_files[0], output, metadata_rows, article, theatre, tei_rng)
        return

    expanded_alto_files = expand_alto_inputs(alto_files)
    if not expanded_alto_files:
        raise click.UsageError("Aucun fichier ALTO XML trouve dans l'entree.")

    # Conversion simple : une entree ALTO donne un seul fichier TEI.
    metadata = select_metadata(metadata_rows, expanded_alto_files)
    tree = build_tei(expanded_alto_files, conversion_options(title, metadata, article, theatre))
    if output:
        if output.exists() and output.is_dir():
            raise click.UsageError("-o doit etre un fichier XML pour une conversion simple.")
        write_tei(tree, output)
        validate_written_outputs([output], output, tei_rng)
    else:
        click.echo(ET.tostring(tree, encoding="unicode", pretty_print=True))


def is_batch_directory(alto_files: tuple[Path, ...]) -> bool:
    """Detecte si l'entree est un dossier parent contenant plusieurs documents.

    :param alto_files: chemins donnes a la commande.
    :type alto_files: tuple[Path, ...]

    :return: True si l'entree doit etre traitee en lot, sinon False.
    :rtype: bool
    """
    if len(alto_files) != 1 or not alto_files[0].is_dir():
        return False

    # Un dossier parent contient des sous-dossiers documentaires, pas des pages directes.
    direct_alto_files = expand_alto_inputs([alto_files[0]])
    subdirectories = document_subdirectories(alto_files[0])
    if direct_alto_files and subdirectories:
        raise click.UsageError(
            "Le dossier contient a la fois des ALTO pour un TEI et des sous-dossiers de TEI. "
            "Choisis le dossier ALTO direct ou le dossier parent."
        )
    return bool(subdirectories)


def convert_parent_directory(
    parent_directory: Path,
    output: Path | None,
    metadata_rows: list[dict[str, str]],
    article: bool = False,
    theatre: bool = False,
    tei_rng: Path | None = None,
) -> None:
    """Convertit chaque sous-dossier documentaire en fichier TEI.

    :param parent_directory: dossier qui contient les documents.
    :type parent_directory: Path
    :param output: dossier de sortie, ou None pour creer TEI/.
    :type output: Path | None
    :param metadata_rows: lignes du CSV de metadonnees.
    :type metadata_rows: list[dict[str, str]]
    :param article: active le wrapper div type="article".
    :type article: bool
    :param theatre: active le traitement des pieces de theatre.
    :type theatre: bool
    :param tei_rng: schema RNG TEI global.
    :type tei_rng: Path | None

    :return: None; ecrit un fichier XML par sous-dossier.
    :rtype: None
    """
    output_directory = output or parent_directory / "TEI"
    if output_directory.suffix:
        raise click.UsageError("-o doit etre un dossier de sortie avec un dossier parent.")
    output_directory.mkdir(parents=True, exist_ok=True)

    # Chaque sous-dossier est converti independamment.
    output_files: list[Path] = []
    for document_directory in document_subdirectories(parent_directory):
        alto_files = expand_alto_inputs([document_directory])
        metadata = select_metadata(metadata_rows, alto_files)
        if not metadata:
            raise click.UsageError(f"Aucune ligne de metadonnees trouvee pour {document_directory.name}.")

        title = metadata.get("title") or document_directory.name
        tree = build_tei(alto_files, conversion_options(title, metadata, article, theatre))
        output_file = output_directory / f"{document_directory.name}.xml"
        write_tei(tree, output_file)
        output_files.append(output_file)
        click.echo(f"Ecrit {output_file}")

    validate_written_outputs(output_files, output_directory, tei_rng)


def conversion_options(
    title: str | None,
    metadata: dict[str, str],
    article: bool,
    theatre: bool,
) -> TeiConversion:
    """Regroupe les options CLI dans un objet de conversion.

    :param title: titre TEI choisi par l'utilisateur ou deduit.
    :type title: str | None
    :param metadata: metadonnees retenues pour le document.
    :type metadata: dict[str, str]
    :param article: active le wrapper div type="article".
    :type article: bool
    :param theatre: active le traitement des pieces de theatre.
    :type theatre: bool

    :return: TeiConversion pret a passer a build_tei().
    :rtype: TeiConversion
    """
    return TeiConversion(title=title, metadata=metadata, article=article, theatre=theatre)


def validate_written_outputs(
    output_files: list[Path],
    output_path: Path,
    tei_rng: Path | None,
) -> None:
    """Valide les TEI ecrits et produit un rapport texte.

    :param output_files: fichiers TEI produits.
    :type output_files: list[Path]
    :param output_path: fichier ou dossier de sortie demande.
    :type output_path: Path
    :param tei_rng: schema RNG fourni, ou None pour detection automatique.
    :type tei_rng: Path | None

    :return: None; ecrit le rapport RNG.
    :rtype: None
    """
    rng_path = resolve_tei_rng_path(tei_rng)
    report_path = validation_report_path(output_path)
    results = validate_tei_files(output_files, rng_path) if rng_path is not None else []
    write_rng_report(report_path, rng_path, results)
    click.echo(f"Rapport RNG {report_path}")


if __name__ == "__main__":
    main()
