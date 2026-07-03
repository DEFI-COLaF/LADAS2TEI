from __future__ import annotations

import re
from dataclasses import replace
from typing import Sequence

from ladas2tei.models import AltoBlock, AltoPage


TOP_PAGE_LIMIT = 250
COLUMN_GAP = 300
ARTICLE_COLUMN_GAP = 230
MIN_BLOCKS_FOR_COLUMNS = 6
MIN_BLOCKS_PER_COLUMN = 3
ARTICLE_LABELS = {"Article", "Article-Continued", "Article-MultipleCol"}
ARTICLE_CONTAINER_LABELS = ARTICLE_LABELS | {"TableZone"}


def order_page(page: AltoPage) -> AltoPage:
    """Trie les blocs d'une page standard avant conversion TEI.

    :param page: page ALTO avec blocs non ordonnes.
    :type page: AltoPage

    :return: AltoPage avec blocs filtres et ordonnes.
    :rtype: AltoPage
    """
    blocks = [block for block in page.blocks if not is_empty_ignored_block(block)]
    top_blocks, content_blocks = split_top_of_page(blocks)

    # On choisit d'abord le cas de mise en page, puis seulement le tri.
    if has_article_layout(content_blocks):
        ordered_content = order_article_layout(content_blocks)
    elif has_catalogue_layout(content_blocks):
        # Les titres centres du catalogue ressemblent a de fausses colonnes.
        ordered_content = order_catalogue_blocks(content_blocks)
    else:
        ordered_content = order_by_coordinates(content_blocks)

    ordered = sorted(top_blocks, key=top_block_key) + merge_split_head_blocks(ordered_content)
    return AltoPage(source=page.source, blocks=tuple(ordered))


def order_theatre_page(page: AltoPage) -> AltoPage:
    """Trie les blocs d'une page en mode theatre.

    :param page: page ALTO avec blocs non ordonnes.
    :type page: AltoPage

    :return: AltoPage ordonnee pour associer locuteurs et repliques.
    :rtype: AltoPage
    """
    blocks = [block for block in page.blocks if not is_empty_ignored_block(block)]
    top_blocks, content_blocks = split_top_of_page(blocks)
    ordered = sorted(top_blocks, key=top_block_key) + order_by_coordinates(content_blocks)
    return AltoPage(source=page.source, blocks=tuple(ordered))


def split_top_of_page(blocks: Sequence[AltoBlock]) -> tuple[list[AltoBlock], list[AltoBlock]]:
    """Separe les blocs de haut de page du contenu principal.

    :param blocks: blocs ALTO d'une page.
    :type blocks: Sequence[AltoBlock]

    :return: Deux listes: blocs de haut de page, puis blocs de contenu.
    :rtype: tuple[list[AltoBlock], list[AltoBlock]]
    """
    top_blocks = [block for block in blocks if is_top_page_furniture(block)]
    content_blocks = [block for block in blocks if block not in top_blocks]
    return top_blocks, content_blocks


def is_empty_ignored_block(block: AltoBlock) -> bool:
    """Indique si un bloc vide doit etre ignore.

    :param block: bloc ALTO a tester.
    :type block: AltoBlock

    :return: True si le bloc est vide et inutile pour le TEI.
    :rtype: bool
    """
    if block.text:
        return False
    return block.label not in {"Article", "Article-Continued", "FigureZone", "GraphicZone", "GraphicZone-Part", "TableZone"}


def is_top_page_furniture(block: AltoBlock) -> bool:
    """Detecte les elements de haut de page.

    :param block: bloc ALTO a tester.
    :type block: AltoBlock

    :return: True si le bloc est un titre courant, une dateline ou un numero de page en haut.
    :rtype: bool
    """
    # Un titre courant n'est du haut de page que si ses coordonnees le disent.
    if block.vpos is None or block.vpos > TOP_PAGE_LIMIT:
        return False
    return block.label in {"RunningTitleZone", "MainZone-Dateline"} or (
        block.label == "NumberingZone" and is_page_milestone(block)
    )


def is_page_milestone(block: AltoBlock) -> bool:
    """Verifie si un bloc de numerotation est un numero de page simple.

    :param block: bloc ALTO de numerotation possible.
    :type block: AltoBlock

    :return: True si le texte contient seulement un numero et de la ponctuation.
    :rtype: bool
    """
    text = block.text
    return bool(text and re.search(r"\d+", text) and re.fullmatch(r"[\W_]*\d+[\W_]*", text))


def top_block_key(block: AltoBlock) -> tuple[int, int, int]:
    """Construit la cle de tri des elements de haut de page.

    :param block: bloc ALTO de haut de page.
    :type block: AltoBlock

    :return: Tuple qui place les numeros avant les titres courants.
    :rtype: tuple[int, int, int]
    """
    label_order = {"NumberingZone": 0, "RunningTitleZone": 1}
    return (
        label_order.get(block.label, 9),
        block.vpos if block.vpos is not None else 0,
        block.hpos if block.hpos is not None else 0,
    )


def layout_key(block: AltoBlock) -> tuple[int, int]:
    """Construit la cle de tri simple par coordonnees.

    :param block: bloc ALTO a trier.
    :type block: AltoBlock

    :return: Tuple vpos, hpos pour lire de haut en bas puis de gauche a droite.
    :rtype: tuple[int, int]
    """
    return (block.vpos if block.vpos is not None else 0, block.hpos if block.hpos is not None else 0)


def order_by_coordinates(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Trie les blocs selon leurs coordonnees et leurs colonnes.

    :param blocks: blocs ALTO a ordonner.
    :type blocks: Sequence[AltoBlock]

    :return: Liste de blocs en ordre de lecture.
    :rtype: list[AltoBlock]
    """
    columns = detect_reading_columns(blocks)
    if len(columns) < 2:
        ordered = sorted(blocks, key=layout_key)
    else:
        ordered = sorted(
            (assign_detected_column(block, columns) for block in blocks),
            key=lambda block: (
                block.column or 1,
                block.vpos if block.vpos is not None else 0,
                block.hpos if block.hpos is not None else 0,
            ),
        )
    ordered = move_question_label_before_heading(ordered)
    return ordered


def detect_reading_columns(blocks: Sequence[AltoBlock]) -> list[int]:
    """Detecte les colonnes de lecture d'apres les positions horizontales.

    :param blocks: blocs ALTO avec coordonnees.
    :type blocks: Sequence[AltoBlock]

    :return: Positions moyennes des colonnes detectees, ou liste vide.
    :rtype: list[int]
    """
    positions = sorted(block.hpos for block in blocks if block.hpos is not None and block.text)
    if len(positions) < MIN_BLOCKS_FOR_COLUMNS:
        return []

    # On groupe les positions x separees par un grand espace horizontal.
    groups: list[list[int]] = []
    for position in positions:
        if not groups or position - groups[-1][-1] > COLUMN_GAP:
            groups.append([position])
        else:
            groups[-1].append(position)

    significant_groups = [group for group in groups if len(group) >= MIN_BLOCKS_PER_COLUMN]
    if len(significant_groups) < 2:
        return []
    return [sum(group) // len(group) for group in significant_groups]


def has_catalogue_layout(blocks: Sequence[AltoBlock]) -> bool:
    """Detecte le cas de catalogue observe dans les fixtures.

    :param blocks: blocs ALTO de contenu.
    :type blocks: Sequence[AltoBlock]

    :return: True si la page ressemble au catalogue numerote.
    :rtype: bool
    """
    labels = {block.label for block in blocks}
    return "MainZone-PStructured" in labels and "MainZone-Item" in labels and "MainZone-Head" in labels


def has_article_layout(blocks: Sequence[AltoBlock]) -> bool:
    """Detecte une page contenant des conteneurs d'article.

    :param blocks: blocs ALTO de contenu.
    :type blocks: Sequence[AltoBlock]

    :return: True si un label Article est present.
    :rtype: bool
    """
    return any(block.label in ARTICLE_LABELS for block in blocks)


def order_article_layout(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Trie les blocs d'une page d'articles.

    :param blocks: blocs ALTO contenant des labels Article.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs ordonnes en respectant articles, colonnes et conteneurs.
    :rtype: list[AltoBlock]
    """
    # Les conteneurs d'article indiquent mieux les colonnes que les blocs de texte.
    columns = detect_article_columns(blocks)
    ordered_blocks = [assign_detected_column(block, columns) for block in blocks]

    # On recopie la colonne du conteneur vers les blocs qu'il contient.
    ordered_blocks = assign_container_columns(ordered_blocks)
    ordered_blocks = normalize_article_continuations(ordered_blocks)

    # Les elements avant le premier article restent en tete de page.
    pre_article, article_blocks = split_before_first_article(ordered_blocks)
    ordered = sorted(pre_article, key=lambda block: pre_article_layout_key(block, pre_article))
    ordered.extend(sorted(article_blocks, key=article_layout_key))
    return move_question_label_before_heading(ordered)


def detect_article_columns(blocks: Sequence[AltoBlock]) -> list[int]:
    """Detecte les colonnes dans une page d'articles.

    :param blocks: blocs ALTO de la page article.
    :type blocks: Sequence[AltoBlock]

    :return: Positions horizontales des colonnes detectees.
    :rtype: list[int]
    """
    positions = sorted(block.hpos for block in blocks if block.hpos is not None and block.vpos is not None and block.vpos > 250)
    columns: list[int] = []
    for position in positions:
        if not columns or position - columns[-1] > ARTICLE_COLUMN_GAP:
            columns.append(position)
    return columns or [0]


def split_before_first_article(blocks: Sequence[AltoBlock]) -> tuple[list[AltoBlock], list[AltoBlock]]:
    """Separe ce qui precede le premier article du contenu article.

    :param blocks: blocs ALTO deja prepares.
    :type blocks: Sequence[AltoBlock]

    :return: Deux listes: avant le premier article, puis articles et contenu associe.
    :rtype: tuple[list[AltoBlock], list[AltoBlock]]
    """
    first_article_y = min(
        (
            block.vpos
            for block in blocks
            if block.label in ARTICLE_LABELS and block.vpos is not None
        ),
        default=None,
    )
    if first_article_y is None:
        return [], list(blocks)

    # Tout ce qui est plus haut que le premier article est traite a part.
    before_article = [
        block
        for block in blocks
        if block.label not in ARTICLE_LABELS and block.vpos is not None and block.vpos < first_article_y
    ]
    article_blocks = [block for block in blocks if block not in before_article]
    return before_article, article_blocks


def pre_article_layout_key(block: AltoBlock, blocks: Sequence[AltoBlock]) -> tuple[int, int, int, int, int]:
    """Construit la cle de tri du contenu place avant les articles.

    :param block: bloc ALTO a trier.
    :type block: AltoBlock
    :param blocks: blocs du groupe avant article.
    :type blocks: Sequence[AltoBlock]

    :return: Tuple de tri tenant compte des tables et colonnes.
    :rtype: tuple[int, int, int, int, int]
    """
    group_y = block.vpos if block.vpos is not None else 0
    if block.label in {"TableZone-Head", "TableZone-P"}:
        table = smallest_containing_container(block, [candidate for candidate in blocks if candidate.label == "TableZone"])
        if table is not None and table.vpos is not None:
            group_y = table.vpos
    return (
        group_y,
        pre_article_label_order(block),
        block.column or 1,
        block.vpos if block.vpos is not None else 0,
        block.hpos if block.hpos is not None else 0,
    )


def pre_article_label_order(block: AltoBlock) -> int:
    """Fixe l'ordre interne des labels avant les articles.

    :param block: bloc ALTO a classer.
    :type block: AltoBlock

    :return: Rang numerique du label.
    :rtype: int
    """
    if block.label == "TableZone":
        return 0
    if block.label == "TableZone-Head":
        return 1
    if block.label == "TableZone-P":
        return 2
    return article_label_order(block)


def assign_detected_column(block: AltoBlock, columns: Sequence[int]) -> AltoBlock:
    """Associe un bloc a la colonne detectee la plus proche.

    :param block: bloc ALTO a annoter.
    :type block: AltoBlock
    :param columns: positions horizontales des colonnes.
    :type columns: Sequence[int]

    :return: Bloc avec le champ column renseigne.
    :rtype: AltoBlock
    """
    if block.hpos is None:
        return block
    column = min(range(len(columns)), key=lambda index: abs(block.hpos - columns[index])) + 1
    return replace(block, column=column)


def assign_container_columns(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Transmet la colonne d'un conteneur a ses blocs internes.

    :param blocks: blocs ALTO, dont certains sont des conteneurs.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs avec colonnes heritees si possible.
    :rtype: list[AltoBlock]
    """
    containers = [
        block
        for block in blocks
        if block.label in ARTICLE_CONTAINER_LABELS and block.column is not None
    ]
    assigned = []
    for block in blocks:
        # Un bloc interne herite de la colonne de son conteneur.
        container = smallest_containing_container(block, containers)
        if container is None or block.label in ARTICLE_CONTAINER_LABELS:
            assigned.append(block)
        else:
            assigned.append(replace(block, column=container.column))
    return assigned


def smallest_containing_container(block: AltoBlock, containers: Sequence[AltoBlock]) -> AltoBlock | None:
    """Trouve le plus petit conteneur qui englobe un bloc.

    :param block: bloc ALTO a rattacher.
    :type block: AltoBlock
    :param containers: conteneurs candidats.
    :type containers: Sequence[AltoBlock]

    :return: Conteneur le plus petit, ou None.
    :rtype: AltoBlock | None
    """
    candidates = [container for container in containers if container is not block and contains_block(container, block)]
    if not candidates:
        return None
    return min(candidates, key=lambda container: (container.width or 0) * (container.height or 0))


def normalize_article_continuations(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Transforme certains articles sans titre en continuations.

    :param blocks: blocs ALTO d'une page article.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs avec labels Article-Continued si necessaire.
    :rtype: list[AltoBlock]
    """
    return [
        replace(block, label="Article-Continued")
        if block.label == "Article" and not contains_label(block, blocks, "MainZone-Head")
        else block
        for block in blocks
    ]


def article_layout_key(block: AltoBlock) -> tuple[int, int, int, int]:
    """Construit la cle de tri du contenu article.

    :param block: bloc ALTO dans une page article.
    :type block: AltoBlock

    :return: Tuple colonne, position verticale, position horizontale et rang label.
    :rtype: tuple[int, int, int, int]
    """
    return (
        block.column or 1,
        block.vpos if block.vpos is not None else 0,
        block.hpos if block.hpos is not None else 0,
        article_label_order(block),
    )


def article_label_order(block: AltoBlock) -> int:
    """Place les conteneurs article avant leur contenu.

    :param block: bloc ALTO a classer.
    :type block: AltoBlock

    :return: Rang numerique du bloc.
    :rtype: int
    """
    if block.label in ARTICLE_CONTAINER_LABELS or block.label in {"FigureZone", "GraphicZone"}:
        return 0
    return 1


def contains_label(container: AltoBlock, blocks: Sequence[AltoBlock], label: str) -> bool:
    """Cherche un label donne a l'interieur d'un conteneur.

    :param container: bloc conteneur.
    :type container: AltoBlock
    :param blocks: blocs a inspecter.
    :type blocks: Sequence[AltoBlock]
    :param label: label LADaS recherche.
    :type label: str

    :return: True si un bloc du label est contenu dans container.
    :rtype: bool
    """
    return any(block.label == label and contains_block(container, block) for block in blocks)


def contains_block(container: AltoBlock, block: AltoBlock) -> bool:
    """Teste si le centre d'un bloc est dans un conteneur.

    :param container: bloc ALTO conteneur.
    :type container: AltoBlock
    :param block: bloc ALTO a tester.
    :type block: AltoBlock

    :return: True si block est spatialement dans container.
    :rtype: bool
    """
    if None in (container.hpos, container.vpos, container.width, container.height, block.hpos, block.vpos):
        return False
    x = block.hpos + (block.width or 0) / 2
    y = block.vpos + (block.height or 0) / 2
    return (
        container.hpos <= x <= container.hpos + container.width
        and container.vpos <= y <= container.vpos + container.height
    )


def order_catalogue_blocks(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Ordonne le cas catalogue avec titres et liste numerotee.

    :param blocks: blocs ALTO d'une page catalogue.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs remis dans l'ordre attendu pour le TEI.
    :rtype: list[AltoBlock]
    """
    heads = [index for index, block in enumerate(blocks) if block.label == "MainZone-Head"]
    if not heads:
        return list(blocks)

    ordered: list[AltoBlock] = []
    first_head = heads[0]
    ordered.append(blocks[first_head])
    ordered.extend(blocks[:first_head])

    for position, head_index in enumerate(heads[1:], start=1):
        previous_head = heads[position - 1]
        next_head = heads[position + 1] if position + 1 < len(heads) else len(blocks)
        before_head = [block for block in blocks[previous_head + 1 : head_index] if block.label != "MainZone-Head"]
        after_head = [block for block in blocks[head_index + 1 : next_head] if block.label != "MainZone-Head"]
        ordered.append(blocks[head_index])
        if position == len(heads) - 1:
            ordered.extend(block for block in before_head + after_head if block.label == "MainZone-Item")
        else:
            ordered.extend(block for block in before_head + after_head if block.label != "MainZone-Item")
    return ordered


def merge_split_head_blocks(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Fusionne deux blocs de titre lorsqu'un titre est coupe.

    :param blocks: blocs ALTO deja ordonnes.
    :type blocks: Sequence[AltoBlock]

    :return: Liste ou certains titres voisins sont fusionnes.
    :rtype: list[AltoBlock]
    """
    merged: list[AltoBlock] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        # Certains titres sont coupes en deux blocs par l'OCR.
        if (
            block.label == "MainZone-Head"
            and block.lines
            and block.lines[-1].lstrip().startswith("(")
            and index + 1 < len(blocks)
            and blocks[index + 1].label == "MainZone-Head"
        ):
            next_block = blocks[index + 1]
            lines = (*block.lines[:-1], *next_block.lines, block.lines[-1])
            merged.append(replace(block, lines=lines))
            index += 2
            continue
        merged.append(block)
        index += 1
    return merged


def move_question_label_before_heading(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Replace une etiquette de question juste avant son titre.

    :param blocks: blocs ALTO ordonnes.
    :type blocks: Sequence[AltoBlock]

    :return: Liste avec certains couples etiquette/titre inverses.
    :rtype: list[AltoBlock]
    """
    ordered: list[AltoBlock] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        # Une etiquette de question peut etre detectee juste apres son titre.
        if (
            block.label == "MainZone-Head"
            and index + 1 < len(blocks)
            and blocks[index + 1].label == "MainZone-PLabelled"
            and same_column(block, blocks[index + 1])
            and close_vertically(block, blocks[index + 1], limit=90)
        ):
            ordered.append(blocks[index + 1])
            ordered.append(block)
            index += 2
            continue
        ordered.append(block)
        index += 1
    return ordered


def same_column(left: AltoBlock, right: AltoBlock) -> bool:
    """Compare la colonne de deux blocs.

    :param left: premier bloc ALTO.
    :type left: AltoBlock
    :param right: second bloc ALTO.
    :type right: AltoBlock

    :return: True si les deux blocs ont la meme colonne detectee.
    :rtype: bool
    """
    return left.column is not None and left.column == right.column


def close_vertically(left: AltoBlock, right: AltoBlock, limit: int) -> bool:
    """Teste si deux blocs sont proches verticalement.

    :param left: bloc situe avant.
    :type left: AltoBlock
    :param right: bloc situe apres.
    :type right: AltoBlock
    :param limit: distance verticale maximale.
    :type limit: int

    :return: True si right suit left a moins de limit.
    :rtype: bool
    """
    if left.vpos is None or right.vpos is None:
        return False
    return 0 < right.vpos - left.vpos < limit
