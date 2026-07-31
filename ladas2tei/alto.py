from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from lxml import etree as ET

from ladas2tei.constantes import ALTO_NS
from ladas2tei.models import AltoBlock, AltoPage

IGNORED_DOCUMENT_SUBDIRECTORIES = {"alto", "img", "image", "images", "tei"}
IGNORED_ALTO_FILENAMES = {"mets.xml"}


def natural_key(path: str | Path) -> tuple[str | int, ...]:
    """Construit une cle pour trier les noms avec nombres dans l'ordre humain.

    :param path: chemin ou nom de fichier a trier.
    :type path: str | Path

    :return: Tuple comparable, par exemple pour placer page_2 avant page_10.
    :rtype: tuple[str | int, ...]
    """
    filename = Path(path).name
    parts = re.split(r"(\d+)", filename)
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def sort_alto_files(paths: Iterable[str | Path]) -> list[Path]:
    """Trie une liste de chemins ALTO avec natural_key().

    :param paths: chemins des fichiers ALTO.
    :type paths: Iterable[str | Path]

    :return: Liste de Path triee naturellement.
    :rtype: list[Path]
    """
    return sorted((Path(path) for path in paths), key=natural_key)


def keep_alto_file(path: str | Path) -> bool:
    """Indique si un fichier XML doit etre traite comme une page ALTO.

    :param path: chemin du fichier XML a tester.
    :type path: str | Path

    :return: True si le fichier doit etre converti.
    :rtype: bool
    """
    return Path(path).name.lower() not in IGNORED_ALTO_FILENAMES


def alto_files_in_directory(directory: str | Path) -> list[Path]:
    """Cherche les fichiers XML ALTO dans un dossier.

    :param directory: dossier a inspecter.
    :type directory: str | Path

    :return: XML trouves directement dans le dossier ou dans son sous-dossier alto/.
    :rtype: list[Path]
    """
    directory_path = Path(directory)

    # METS.xml decrit l'export, mais ce n'est pas une page ALTO a convertir.
    direct_xml_files = sort_alto_files(path for path in directory_path.glob("*.xml") if keep_alto_file(path))
    if direct_xml_files:
        return direct_xml_files

    alto_directory = directory_path / "alto"
    if alto_directory.is_dir():
        return sort_alto_files(path for path in alto_directory.glob("*.xml") if keep_alto_file(path))
    return []


def document_subdirectories(directory: str | Path) -> list[Path]:
    """Trouve les sous-dossiers correspondant a des documents.

    :param directory: dossier parent a inspecter.
    :type directory: str | Path

    :return: Sous-dossiers qui contiennent des fichiers ALTO.
    :rtype: list[Path]
    """
    directory_path = Path(directory)
    subdirectories = [
        path
        for path in directory_path.iterdir()
        if path.is_dir() and path.name.lower() not in IGNORED_DOCUMENT_SUBDIRECTORIES
    ]
    document_dirs = [path for path in subdirectories if alto_files_in_directory(path)]
    return sort_alto_files(document_dirs)


def expand_alto_inputs(paths: Sequence[str | Path]) -> list[Path]:
    """Remplace les dossiers d'entree par leurs fichiers ALTO.

    :param paths: fichiers ALTO ou dossiers.
    :type paths: Sequence[str | Path]

    :return: Liste triee de fichiers XML ALTO.
    :rtype: list[Path]
    """
    alto_files: list[Path] = []
    for path in paths:
        input_path = Path(path)
        if input_path.is_dir():
            alto_files.extend(alto_files_in_directory(input_path))
        else:
            alto_files.append(input_path)
    return sort_alto_files(alto_files)


def parse_alto(path: str | Path) -> AltoPage:
    """Lit un fichier ALTO et extrait ses blocs LADaS utiles.

    :param path: chemin vers un fichier XML ALTO.
    :type path: str | Path

    :return: AltoPage contenant la source et les blocs reconnus.
    :rtype: AltoPage
    """
    xml_path = Path(path)
    tree = ET.parse(str(xml_path))

    # Les OtherTag donnent la correspondance entre les TAGREFS et les labels LADaS.
    labels = {
        tag.get("ID"): tag.get("LABEL")
        for tag in tree.xpath("//alto:OtherTag", namespaces={"alto": ALTO_NS})
        if tag.get("ID") and tag.get("LABEL")
    }
    blocks = []
    unlabeled_lines = []

    # Chaque TextBlock devient un AltoBlock, avec texte et coordonnees.
    for block in tree.xpath("//alto:TextBlock", namespaces={"alto": ALTO_NS}):
        label = label_for(block.get("TAGREFS"), labels)
        lines = tuple(
            line_text(line)
            for line in block.xpath("./alto:TextLine", namespaces={"alto": ALTO_NS})
        )
        if not label:
            # Certaines lignes sont dans un bloc sans label : on essaie de les rattacher ensuite.
            unlabeled_lines.extend(parse_unlabeled_lines(block))
            continue
        blocks.append(
            AltoBlock(
                label=label,
                lines=lines,
                block_id=block.get("ID"),
                hpos=parse_int(block.get("HPOS")),
                vpos=parse_int(block.get("VPOS")),
                width=parse_int(block.get("WIDTH")),
                height=parse_int(block.get("HEIGHT")),
            )
        )
    blocks.extend(blocks_from_unlabeled_lines(unlabeled_lines, blocks))
    return AltoPage(source=xml_path, blocks=tuple(blocks))


def parse_int(value: str | None) -> int | None:
    """Convertit une valeur ALTO numerique en entier.

    :param value: chaine ALTO, souvent une coordonnee.
    :type value: str | None

    :return: Entier converti, ou None si la valeur est absente/invalide.
    :rtype: int | None
    """
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def label_for(tagrefs: str | None, labels: dict[str, str]) -> str | None:
    """Associe un TAGREFS ALTO a son label LADaS.

    :param tagrefs: identifiants TAGREFS portes par un bloc.
    :type tagrefs: str | None
    :param labels: dictionnaire ID ALTO vers label LADaS.
    :type labels: dict[str, str]

    :return: Label LADaS trouve, ou None.
    :rtype: str | None
    """
    if not tagrefs:
        return None
    for tagref in tagrefs.split():
        if tagref in labels:
            return labels[tagref]
    return None


def line_text(line: ET._Element) -> str:
    """Reconstruit le texte d'une ligne ALTO.

    :param line: element TextLine ALTO.
    :type line: ET._Element

    :return: Texte de la ligne avec les espaces SP.
    :rtype: str
    """
    parts = []
    for child in line:
        local = ET.QName(child).localname
        # ALTO separe les mots et les espaces dans deux types de balises.
        if local == "String":
            parts.append(child.get("CONTENT", ""))
        elif local == "SP":
            parts.append(" ")
    return "".join(parts)


def parse_unlabeled_lines(block: ET._Element) -> list[AltoBlock]:
    """Transforme les lignes sans label de bloc en blocs provisoires.

    :param block: TextBlock ALTO sans label exploitable.
    :type block: ET._Element

    :return: Blocs AltoBlock portant les coordonnees des lignes.
    :rtype: list[AltoBlock]
    """
    lines = []
    for line in block.xpath("./alto:TextLine", namespaces={"alto": ALTO_NS}):
        text = line_text(line).strip()
        if not text:
            continue
        lines.append(
            AltoBlock(
                label="",
                lines=(text,),
                block_id=line.get("ID") or block.get("ID"),
                hpos=parse_int(line.get("HPOS")),
                vpos=parse_int(line.get("VPOS")),
                width=parse_int(line.get("WIDTH")),
                height=parse_int(line.get("HEIGHT")),
            )
        )
    return lines


def blocks_from_unlabeled_lines(lines: Sequence[AltoBlock], containers: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Rattache des lignes sans label au plus petit conteneur connu.

    :param lines: lignes ALTO sans label direct.
    :type lines: Sequence[AltoBlock]
    :param containers: blocs ALTO deja labels.
    :type containers: Sequence[AltoBlock]

    :return: Blocs recuperes avec un label deduit du conteneur.
    :rtype: list[AltoBlock]
    """
    recovered = []
    for line in lines:
        container = smallest_containing_block(line, containers)
        if container is None:
            continue
        recovered.append(
            AltoBlock(
                label=recovered_label(container.label),
                lines=line.lines,
                block_id=line.block_id,
                hpos=line.hpos,
                vpos=line.vpos,
                width=line.width,
                height=line.height,
            )
        )
    return recovered


def recovered_label(container_label: str) -> str:
    """Choisit le label d'une ligne recuperee depuis son conteneur.

    :param container_label: label LADaS du bloc conteneur.
    :type container_label: str

    :return: Label a donner a la ligne recuperee.
    :rtype: str
    """
    if container_label == "TableZone":
        return "TableZone-P"
    return container_label


def smallest_containing_block(line: AltoBlock, containers: Sequence[AltoBlock]) -> AltoBlock | None:
    """Trouve le plus petit bloc qui contient une ligne.

    :param line: ligne transformee en AltoBlock.
    :type line: AltoBlock
    :param containers: blocs candidats autour de la ligne.
    :type containers: Sequence[AltoBlock]

    :return: Plus petit conteneur trouve, ou None.
    :rtype: AltoBlock | None
    """
    candidates = [block for block in containers if block_contains(block, line)]
    if not candidates:
        return None
    return min(candidates, key=lambda block: (block.width or 0) * (block.height or 0))


def block_contains(container: AltoBlock, line: AltoBlock) -> bool:
    """Teste si le centre d'une ligne est dans un bloc conteneur.

    :param container: bloc ALTO candidat.
    :type container: AltoBlock
    :param line: ligne ALTO a tester.
    :type line: AltoBlock

    :return: True si la ligne est dans le conteneur.
    :rtype: bool
    """
    if None in (container.hpos, container.vpos, container.width, container.height, line.hpos, line.vpos):
        return False
    x = line.hpos + (line.width or 0) / 2
    y = line.vpos + (line.height or 0) / 2
    return (
        container.hpos <= x <= container.hpos + container.width
        and container.vpos <= y <= container.vpos + container.height
    )
