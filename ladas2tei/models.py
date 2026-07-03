from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TeiElementSpec:
    """Decrit l'element TEI a creer pour un label LADaS.

    :param path: chemin d'elements TEI a creer.
    :type path: tuple[str, ...]
    :param attrs: attributs XML du premier element.
    :type attrs: tuple[tuple[str, str], ...]
    :param wrapper_path: element parent a creer avant path.
    :type wrapper_path: tuple[str, ...]

    :return: Specification reutilisee par le convertisseur TEI.
    :rtype: TeiElementSpec
    """

    path: tuple[str, ...]
    attrs: tuple[tuple[str, str], ...] = ()
    wrapper_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class AltoBlock:
    """Represente un bloc ALTO annote LADaS.

    :param label: label LADaS du bloc.
    :type label: str
    :param lines: lignes OCR du bloc.
    :type lines: tuple[str, ...]
    :param block_id: identifiant ALTO.
    :type block_id: str | None
    :param hpos: position horizontale.
    :type hpos: int | None
    :param vpos: position verticale.
    :type vpos: int | None
    :param width: largeur du bloc.
    :type width: int | None
    :param height: hauteur du bloc.
    :type height: int | None
    :param column: colonne de lecture detectee.
    :type column: int | None

    :return: Objet de travail pour l'ordre et la conversion TEI.
    :rtype: AltoBlock
    """

    label: str
    lines: tuple[str, ...]
    block_id: str | None = None
    hpos: int | None = None
    vpos: int | None = None
    width: int | None = None
    height: int | None = None
    column: int | None = None

    @property
    def text(self) -> str:
        """Joint les lignes OCR pour obtenir le texte du bloc.

        :param self: bloc ALTO courant.
        :type self: objet courant

        :return: Texte du bloc sans lignes vides.
        :rtype: str
        """
        return " ".join(line for line in self.lines if line).strip()


@dataclass(frozen=True)
class AltoPage:
    """Regroupe les blocs ALTO d'une page.

    :param source: fichier ALTO source.
    :type source: Path
    :param blocks: blocs extraits de la page.
    :type blocks: tuple[AltoBlock, ...]

    :return: Page prete pour le tri et la conversion.
    :rtype: AltoPage
    """

    source: Path
    blocks: tuple[AltoBlock, ...]


@dataclass
class TeiConversion:
    """Regroupe les options d'une conversion TEI.

    :param title: titre force ou None.
    :type title: str | None
    :param metadata: metadonnees du document.
    :type metadata: dict[str, str]
    :param article: active le wrapper article.
    :type article: bool
    :param theatre: active le mode theatre.
    :type theatre: bool

    :return: Configuration passee a build_tei().
    :rtype: TeiConversion
    """

    title: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    article: bool = False
    theatre: bool = False
