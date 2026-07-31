"""Ordre de lecture des blocs ALTO.

Ce module ne cree pas de TEI. Il prend une page ALTO deja parse'e et renvoie les
memes blocs dans l'ordre ou `tei.py` doit les consommer.

Regle mentale utile :
- pour une page simple, on trie par colonnes seulement les blocs qui participent
  vraiment a une pile verticale de texte ;
- pour une page d'article, les conteneurs `Article*` priment sur les colonnes :
  un bloc n'entre dans un article que s'il est geometriquement superpose au
  conteneur ;
- le theatre reutilise le tri standard, puis `tei.py` decide locuteur/replique.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Sequence

from ladas2tei.models import AltoBlock, AltoPage


TOP_PAGE_LIMIT = 250
COLUMN_GAP = 300
ARTICLE_COLUMN_GAP = 230
ARTICLE_ROW_GAP = 70
ARTICLE_CONTINUATION_EDGE_TOLERANCE = 40
MIN_COLUMN_STACK_BLOCKS = 2
MIN_COLUMN_BLOCK_HEIGHT = 35
MAX_COLUMN_SPAN_RATIO = 0.62
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
    return block.label not in {
        "Article",
        "Article-Continued",
        "Article-MultipleCol",
        "FigureZone",
        "GraphicZone",
        "GraphicZone-Part",
        "TableZone",
    }


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
    # On commence par la detection la plus fiable : des piles verticales de
    # blocs. Les titres pleine largeur et chapeaux n'appartiennent pas a ces
    # piles et restent donc hors colonnes.
    column_groups = detect_stacked_text_column_groups(blocks)
    columns = [column_group_center(group) for group in column_groups]
    if len(columns) < 2:
        columns = detect_reading_columns(blocks)
        column_groups = []
    if len(columns) < 2:
        ordered = sorted(blocks, key=layout_key)
    else:
        assigned_blocks = [
            assign_column_if_classable(block, columns, column_groups, horizontal_page_span(blocks))
            for block in blocks
        ]
        first_column_y = min(
            (
                block.vpos
                for block in assigned_blocks
                if block.column is not None and block.vpos is not None
            ),
            default=None,
        )
        pre_column_blocks = [
            block
            for block in assigned_blocks
            if block.column is None
            and first_column_y is not None
            and block.vpos is not None
            and block.vpos < first_column_y
        ]
        column_blocks = [block for block in assigned_blocks if block.column is not None]
        other_blocks = [
            block
            for block in assigned_blocks
            if block.column is None and block not in pre_column_blocks
        ]
        ordered = sorted(
            column_blocks,
            key=lambda block: (
                block.column or 1,
                block.vpos if block.vpos is not None else 0,
                block.hpos if block.hpos is not None else 0,
            ),
        )
        ordered = sorted(pre_column_blocks, key=layout_key) + ordered + sorted(other_blocks, key=layout_key)
    ordered = move_question_label_before_heading(ordered)
    return ordered


def detect_reading_columns(blocks: Sequence[AltoBlock]) -> list[int]:
    """Detecte les colonnes de lecture d'apres les positions horizontales.

    :param blocks: blocs ALTO avec coordonnees.
    :type blocks: Sequence[AltoBlock]

    :return: Positions moyennes des colonnes detectees, ou liste vide.
    :rtype: list[int]
    """
    stacked_columns = detect_stacked_text_columns(blocks)
    if len(stacked_columns) >= 2:
        return stacked_columns

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

    # On recopie la colonne du conteneur vers les blocs qu'il contient, puis on
    # retire explicitement les blocs qui ne tombent dans aucun article. Cette
    # marque `column=None` permettra a `tei.py` de sortir du div article courant.
    ordered_blocks = assign_container_columns(ordered_blocks)
    ordered_blocks = clear_orphan_article_columns(ordered_blocks)
    ordered_blocks = normalize_article_continuations(ordered_blocks)
    ordered_blocks = normalize_continued_article_content(ordered_blocks)

    # Les elements avant le premier article restent en tete de page.
    pre_article, article_blocks = split_before_first_article(ordered_blocks)
    ordered = sorted(pre_article, key=lambda block: pre_article_layout_key(block, pre_article))
    ordered.extend(order_article_sections(article_blocks))
    return move_question_label_before_heading(ordered)


def order_article_sections(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Ordonne les conteneurs d'articles et leur contenu.

    :param blocks: blocs de la partie article d'une page.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs ordonnes par article et par bande de lecture.
    :rtype: list[AltoBlock]
    """
    if any(block.label in {"Article-MultipleCol", "Article-Continued"} for block in blocks):
        return order_article_rows(blocks)
    return sorted(blocks, key=article_layout_key)


def order_article_rows(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Trie les articles par rangées, puis de gauche à droite dans chaque rangée.

    :param blocks: blocs d'articles, incluant les articles multicolonnes.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs ordonnes.
    :rtype: list[AltoBlock]
    """
    containers = sorted(article_containers(blocks), key=article_container_key)
    base_containers = [container for container in containers if container.label != "Article-Continued"]
    continued_by_target = group_continued_articles(base_containers, containers)
    grouped_continuation_ids = {
        id(continued)
        for continuations in continued_by_target.values()
        for continued in continuations
    }
    rows = group_article_rows(containers)
    ordered: list[AltoBlock] = []
    used: set[int] = set()
    for row in rows:
        for container in sorted(row, key=lambda block: block.hpos if block.hpos is not None else 0):
            if id(container) in grouped_continuation_ids:
                continue
            ordered.extend(article_with_content(container, blocks))
            used.add(id(container))
            for child in contained_article_content(container, blocks):
                used.add(id(child))
            for continued in continued_by_target.get(id(container), []):
                ordered.extend(article_with_content(continued, blocks))
                used.add(id(continued))
                for child in contained_article_content(continued, blocks):
                    used.add(id(child))
    leftovers = [block for block in blocks if id(block) not in used]
    ordered.extend(sorted(leftovers, key=article_layout_key))
    return ordered


def group_continued_articles(
    base_containers: Sequence[AltoBlock],
    containers: Sequence[AltoBlock],
) -> dict[int, list[AltoBlock]]:
    """Rattache chaque Article-Continued a l'article precedent le plus probable.

    :param base_containers: articles avec leur propre debut.
    :type base_containers: Sequence[AltoBlock]
    :param containers: tous les conteneurs d'article.
    :type containers: Sequence[AltoBlock]

    :return: Continuations regroupees par identifiant d'article cible.
    :rtype: dict[int, list[AltoBlock]]
    """
    grouped: dict[int, list[AltoBlock]] = {}
    for continued in [block for block in containers if block.label == "Article-Continued"]:
        target = continued_article_target(continued, base_containers)
        if target is None:
            continue
        grouped.setdefault(id(target), []).append(continued)
    for continuations in grouped.values():
        continuations.sort(key=lambda block: (block.column or 1, block.vpos or 0, block.hpos or 0))
    return grouped


def continued_article_target(
    continued: AltoBlock,
    candidates: Sequence[AltoBlock],
) -> AltoBlock | None:
    """Trouve l'article a gauche qu'une continuation doit prolonger.

    :param continued: conteneur Article-Continued.
    :type continued: AltoBlock
    :param candidates: articles cibles possibles.
    :type candidates: Sequence[AltoBlock]

    :return: Article cible ou None.
    :rtype: AltoBlock | None
    """
    viable = [
        candidate
        for candidate in candidates
        if candidate.label != "Article-Continued" and is_left_continuation_target(candidate, continued)
    ]
    if not viable:
        return None
    return min(viable, key=lambda candidate: (horizontal_gap(candidate, continued), vertical_gap(candidate, continued)))


def is_left_continuation_target(candidate: AltoBlock, continued: AltoBlock) -> bool:
    """Verifie si une continuation peut prolonger l'article a sa gauche.

    :param candidate: article candidat.
    :type candidate: AltoBlock
    :param continued: continuation.
    :type continued: AltoBlock

    :return: True si la geometrie ressemble a une continuation de colonne.
    :rtype: bool
    """
    if None in (candidate.hpos, candidate.vpos, candidate.width, candidate.height, continued.hpos, continued.vpos):
        return False
    if block_left(candidate) > block_left(continued):
        return False
    if block_right(candidate) > block_left(continued) + ARTICLE_CONTINUATION_EDGE_TOLERANCE:
        return False
    gap = horizontal_gap(candidate, continued)
    if gap > ARTICLE_COLUMN_GAP:
        return False
    return vertical_gap(candidate, continued) <= ARTICLE_ROW_GAP * 2


def horizontal_gap(left: AltoBlock, right: AltoBlock) -> int:
    """Calcule la distance horizontale entre deux blocs.

    :param left: bloc de gauche.
    :type left: AltoBlock
    :param right: bloc de droite.
    :type right: AltoBlock

    :return: Distance entre bords, 0 si chevauchement.
    :rtype: int
    """
    return max(0, block_left(right) - block_right(left))


def vertical_gap(left: AltoBlock, right: AltoBlock) -> int:
    """Calcule la distance verticale entre deux blocs.

    :param left: premier bloc.
    :type left: AltoBlock
    :param right: second bloc.
    :type right: AltoBlock

    :return: Distance verticale hors chevauchement.
    :rtype: int
    """
    if None in (left.vpos, left.height, right.vpos, right.height):
        return 10**6
    left_top = left.vpos or 0
    right_top = right.vpos or 0
    left_bottom = left_top + (left.height or 0)
    right_bottom = right_top + (right.height or 0)
    return max(0, max(left_top, right_top) - min(left_bottom, right_bottom))


def article_containers(
    blocks: Sequence[AltoBlock],
    labels: set[str] | None = None,
) -> list[AltoBlock]:
    """Retourne les conteneurs d'article d'une liste de blocs.

    :param blocks: blocs ALTO.
    :type blocks: Sequence[AltoBlock]
    :param labels: labels de conteneurs a garder, ou None pour tous les articles.
    :type labels: set[str] | None

    :return: Conteneurs d'article.
    :rtype: list[AltoBlock]
    """
    selected_labels = labels or ARTICLE_LABELS
    return [block for block in blocks if block.label in selected_labels]


def group_article_rows(containers: Sequence[AltoBlock]) -> list[list[AltoBlock]]:
    """Regroupe les conteneurs d'article par bandes verticales proches.

    :param containers: conteneurs d'article.
    :type containers: Sequence[AltoBlock]

    :return: Rangées de conteneurs.
    :rtype: list[list[AltoBlock]]
    """
    rows: list[list[AltoBlock]] = []
    for container in sorted(containers, key=article_container_key):
        if not rows or not same_article_row(container, rows[-1]):
            rows.append([container])
        else:
            rows[-1].append(container)
    return rows


def same_article_row(container: AltoBlock, row: Sequence[AltoBlock]) -> bool:
    """Teste si un conteneur appartient a une rangee d'articles.

    :param container: conteneur a classer.
    :type container: AltoBlock
    :param row: rangee candidate.
    :type row: Sequence[AltoBlock]

    :return: True si les zones verticales sont proches ou se chevauchent.
    :rtype: bool
    """
    if not row:
        return False
    return abs((container.vpos or 0) - row_top(row)) <= ARTICLE_ROW_GAP


def row_top(row: Sequence[AltoBlock]) -> int:
    """Calcule le haut moyen d'une rangée d'articles.

    :param row: conteneurs d'une même rangée.
    :type row: Sequence[AltoBlock]

    :return: Position verticale moyenne.
    :rtype: int
    """
    values = [block.vpos for block in row if block.vpos is not None]
    if not values:
        return 0
    return sum(values) // len(values)


def article_with_content(container: AltoBlock, blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Retourne un conteneur article suivi de ses blocs internes.

    :param container: conteneur d'article.
    :type container: AltoBlock
    :param blocks: blocs ALTO de la page.
    :type blocks: Sequence[AltoBlock]

    :return: Conteneur puis contenu ordonne.
    :rtype: list[AltoBlock]
    """
    content = order_article_content(container, contained_article_content(container, blocks))
    return [container, *content]


def order_article_content(container: AltoBlock, blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Trie le contenu direct d'un article en tenant compte de ses colonnes internes.

    :param container: conteneur article.
    :type container: AltoBlock
    :param blocks: contenu direct du conteneur.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs internes ordonnes.
    :rtype: list[AltoBlock]
    """
    columns = detect_stacked_text_columns(blocks)
    if len(columns) < 2:
        columns = detect_article_columns(blocks)
    if len(columns) < 2:
        return sorted(blocks, key=article_content_key)

    assigned = [assign_detected_column(block, columns) for block in blocks]
    return sorted(
        assigned,
        key=lambda block: (
            article_label_order(block),
            block.column or 1,
            block.vpos if block.vpos is not None else 0,
            block.hpos if block.hpos is not None else 0,
        ),
    )


def contained_article_content(container: AltoBlock, blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Trouve les blocs internes directs d'un article.

    :param container: conteneur d'article.
    :type container: AltoBlock
    :param blocks: blocs ALTO de la page.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs contenus sans autres conteneurs d'article.
    :rtype: list[AltoBlock]
    """
    inner_articles = [
        block
        for block in article_containers(blocks)
        if block is not container and contains_block(container, block)
    ]
    return [
        block
        for block in blocks
        if (
            block is not container
            and block.label not in ARTICLE_LABELS
            and contains_block(container, block)
            and not any(contains_block(article, block) for article in inner_articles)
        )
    ]


def article_container_key(block: AltoBlock) -> tuple[int, int, int]:
    """Construit la cle de tri d'un conteneur d'article.

    :param block: conteneur ALTO.
    :type block: AltoBlock

    :return: Tuple position verticale, horizontale, ordre de label.
    :rtype: tuple[int, int, int]
    """
    return (
        block.vpos if block.vpos is not None else 0,
        block.hpos if block.hpos is not None else 0,
        article_label_order(block),
    )


def article_content_key(block: AltoBlock) -> tuple[int, int, int, int]:
    """Construit la cle de tri du contenu interne d'un article.

    :param block: bloc interne d'un article.
    :type block: AltoBlock

    :return: Tuple ordre label, vertical, horizontal, colonne.
    :rtype: tuple[int, int, int, int]
    """
    return (
        article_label_order(block),
        block.column or 1,
        block.vpos if block.vpos is not None else 0,
        block.hpos if block.hpos is not None else 0,
    )


def detect_article_columns(blocks: Sequence[AltoBlock]) -> list[int]:
    """Detecte les colonnes dans une page d'articles.

    :param blocks: blocs ALTO de la page article.
    :type blocks: Sequence[AltoBlock]

    :return: Positions horizontales des colonnes detectees.
    :rtype: list[int]
    """
    stacked_columns = detect_stacked_text_columns(
        [block for block in blocks if block.label not in {"Article-MultipleCol"}]
    )
    if len(stacked_columns) >= 2:
        return stacked_columns

    positions = sorted(block.hpos for block in blocks if block.hpos is not None and block.vpos is not None and block.vpos > 250)
    columns: list[int] = []
    for position in positions:
        if not columns or position - columns[-1] > ARTICLE_COLUMN_GAP:
            columns.append(position)
    return columns or [0]


def detect_stacked_text_columns(blocks: Sequence[AltoBlock]) -> list[int]:
    """Detecte des colonnes comme des piles verticales de gros blocs textuels.

    :param blocks: blocs ALTO a analyser.
    :type blocks: Sequence[AltoBlock]

    :return: Centres horizontaux des colonnes significatives.
    :rtype: list[int]
    """
    significant_groups = detect_stacked_text_column_groups(blocks)
    return [column_group_center(group) for group in significant_groups]


def detect_stacked_text_column_groups(blocks: Sequence[AltoBlock]) -> list[list[AltoBlock]]:
    """Detecte les piles de blocs qui constituent vraiment des colonnes.

    :param blocks: blocs ALTO a analyser.
    :type blocks: Sequence[AltoBlock]

    :return: Groupes de blocs classables en colonnes.
    :rtype: list[list[AltoBlock]]
    """
    candidates = column_stack_candidates(blocks)
    if len(candidates) < MIN_COLUMN_STACK_BLOCKS * 2:
        return []

    groups: list[list[AltoBlock]] = []
    for block in sorted(candidates, key=lambda candidate: block_left(candidate)):
        for group in groups:
            if belongs_to_column_stack(block, group):
                group.append(block)
                break
        else:
            groups.append([block])

    significant_groups = [group for group in groups if is_significant_column_stack(group)]
    if len(significant_groups) < 2:
        return []
    return significant_groups


def column_stack_candidates(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Garde les blocs capables de signaler une colonne de lecture.

    :param blocks: blocs ALTO.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs textuels ou conteneurs verticaux utiles.
    :rtype: list[AltoBlock]
    """
    page_span = horizontal_page_span(blocks)
    candidates: list[AltoBlock] = []
    for block in blocks:
        if None in (block.hpos, block.vpos, block.width, block.height):
            continue
        if page_span and (block.width or 0) / page_span > MAX_COLUMN_SPAN_RATIO:
            continue
        if block.label in ARTICLE_CONTAINER_LABELS:
            candidates.append(block)
            continue
        if block.text and (block.height or 0) >= MIN_COLUMN_BLOCK_HEIGHT:
            candidates.append(block)
    return candidates


def block_is_page_wide(block: AltoBlock, page_span: int) -> bool:
    """Indique si un bloc couvre trop la page pour appartenir a une colonne.

    :param block: bloc ALTO.
    :type block: AltoBlock
    :param page_span: largeur utile de la page.
    :type page_span: int

    :return: True si le bloc est un titre ou chapeau pleine largeur probable.
    :rtype: bool
    """
    return bool(page_span and block.width is not None and block.width / page_span > MAX_COLUMN_SPAN_RATIO)


def horizontal_page_span(blocks: Sequence[AltoBlock]) -> int:
    """Estime la largeur utile couverte par les blocs.

    :param blocks: blocs ALTO.
    :type blocks: Sequence[AltoBlock]

    :return: Largeur horizontale utile, ou 0.
    :rtype: int
    """
    left_values = [block.hpos for block in blocks if block.hpos is not None]
    right_values = [
        block.hpos + block.width
        for block in blocks
        if block.hpos is not None and block.width is not None
    ]
    if not left_values or not right_values:
        return 0
    return max(right_values) - min(left_values)


def belongs_to_column_stack(block: AltoBlock, group: Sequence[AltoBlock]) -> bool:
    """Teste si un bloc appartient a une pile verticale existante.

    :param block: bloc candidat.
    :type block: AltoBlock
    :param group: pile de colonne candidate.
    :type group: Sequence[AltoBlock]

    :return: True si le bloc recouvre horizontalement la pile.
    :rtype: bool
    """
    return any(horizontal_overlap_ratio(block, other) >= 0.35 for other in group)


def is_significant_column_stack(group: Sequence[AltoBlock]) -> bool:
    """Valide qu'une pile ressemble vraiment a une colonne.

    :param group: blocs d'une pile candidate.
    :type group: Sequence[AltoBlock]

    :return: True si la pile contient assez de blocs ou de hauteur.
    :rtype: bool
    """
    if len(group) >= MIN_COLUMN_STACK_BLOCKS:
        return True
    heights = [block.height or 0 for block in group]
    return bool(heights and max(heights) >= MIN_COLUMN_BLOCK_HEIGHT * 4)


def column_group_center(group: Sequence[AltoBlock]) -> int:
    """Calcule le centre horizontal moyen d'une pile de colonne.

    :param group: pile de blocs.
    :type group: Sequence[AltoBlock]

    :return: Centre horizontal moyen.
    :rtype: int
    """
    centers = [block_left(block) + ((block.width or 0) // 2) for block in group]
    return sum(centers) // len(centers)


def horizontal_overlap_ratio(left: AltoBlock, right: AltoBlock) -> float:
    """Calcule le taux de recouvrement horizontal de deux blocs.

    :param left: premier bloc.
    :type left: AltoBlock
    :param right: second bloc.
    :type right: AltoBlock

    :return: Recouvrement rapporte a la largeur du plus petit bloc.
    :rtype: float
    """
    if None in (left.hpos, left.width, right.hpos, right.width):
        return 0.0
    overlap = min(block_right(left), block_right(right)) - max(block_left(left), block_left(right))
    if overlap <= 0:
        return 0.0
    width = min(left.width or 0, right.width or 0)
    if width <= 0:
        return 0.0
    return overlap / width


def block_left(block: AltoBlock) -> int:
    """Retourne le bord gauche d'un bloc.

    :param block: bloc ALTO.
    :type block: AltoBlock

    :return: Position horizontale.
    :rtype: int
    """
    return block.hpos if block.hpos is not None else 0


def block_right(block: AltoBlock) -> int:
    """Retourne le bord droit d'un bloc.

    :param block: bloc ALTO.
    :type block: AltoBlock

    :return: Position horizontale droite.
    :rtype: int
    """
    return (block.hpos if block.hpos is not None else 0) + (block.width or 0)


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


def assign_column_if_classable(
    block: AltoBlock,
    columns: Sequence[int],
    column_groups: Sequence[Sequence[AltoBlock]],
    page_span: int = 0,
) -> AltoBlock:
    """Associe une colonne seulement aux blocs qui recouvrent une pile detectee.

    :param block: bloc ALTO a annoter.
    :type block: AltoBlock
    :param columns: centres des colonnes.
    :type columns: Sequence[int]
    :param column_groups: piles de blocs detectees.
    :type column_groups: Sequence[Sequence[AltoBlock]]
    :param page_span: largeur utile de la page.
    :type page_span: int

    :return: Bloc annote si classable en colonne.
    :rtype: AltoBlock
    """
    if not column_groups:
        if block_is_page_wide(block, page_span):
            return replace(block, column=None)
        return assign_detected_column(block, columns)
    for index, group in enumerate(column_groups, start=1):
        if belongs_to_column_stack(block, group):
            return replace(block, column=index)
    return replace(block, column=None)


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


def clear_orphan_article_columns(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Retire la colonne des blocs qui ne sont superposes a aucun article.

    :param blocks: blocs ALTO d'une page article.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs avec les orphelins d'article marques hors colonne.
    :rtype: list[AltoBlock]
    """
    containers = [block for block in blocks if block.label in ARTICLE_CONTAINER_LABELS]
    cleaned: list[AltoBlock] = []
    for block in blocks:
        if block.label in ARTICLE_CONTAINER_LABELS:
            cleaned.append(block)
            continue
        if any(contains_block(container, block) for container in containers):
            cleaned.append(block)
        else:
            cleaned.append(replace(block, column=None))
    return cleaned


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


def normalize_continued_article_content(blocks: Sequence[AltoBlock]) -> list[AltoBlock]:
    """Fait continuer le premier paragraphe d'un Article-Continued.

    :param blocks: blocs ALTO d'une page article.
    :type blocks: Sequence[AltoBlock]

    :return: Blocs ou le premier paragraphe de continuation est marque.
    :rtype: list[AltoBlock]
    """
    continued_containers = [block for block in blocks if block.label == "Article-Continued"]
    first_text_by_container: dict[int, AltoBlock] = {}
    for container in continued_containers:
        text_blocks = sorted(
            [
                block
                for block in blocks
                if block.label == "MainZone-P" and contains_block(container, block)
            ],
            key=article_content_key,
        )
        if text_blocks:
            first_text_by_container[id(container)] = text_blocks[0]

    first_text_ids = {id(block) for block in first_text_by_container.values()}
    return [
        replace(block, label="MainZone-Continued")
        if id(block) in first_text_ids
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
