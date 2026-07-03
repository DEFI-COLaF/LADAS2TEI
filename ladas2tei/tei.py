from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from lxml import etree as ET

from ladas2tei.alto import parse_alto, sort_alto_files
from ladas2tei.constantes import NSMAP, TEI_NS, XML_NS, qname
from ladas2tei.mappings import CUMULATIVE_PARENT_LABELS, EMPTY_TEXT_CONTAINER_LABELS, LADAS_TO_TEI
from ladas2tei.models import AltoBlock, AltoPage, TeiConversion, TeiElementSpec
from ladas2tei.ordering import is_empty_ignored_block, order_page, order_theatre_page


def build_tei(
    alto_files: Sequence[str | Path],
    conversion: TeiConversion | None = None,
) -> ET._ElementTree:
    """Construit un document TEI complet depuis des fichiers ALTO.

    :param alto_files: chemins vers les fichiers ALTO a convertir.
    :type alto_files: Sequence[str | Path]
    :param conversion: options de conversion, ou None pour les options par defaut.
    :type conversion: TeiConversion | None

    :return: Arbre XML TEI complet.
    :rtype: ET._ElementTree
    """
    conversion = conversion or TeiConversion()
    pages = []

    # On lit et on ordonne chaque page avant de commencer a creer le TEI.
    for path in sort_alto_files(alto_files):
        parsed_page = parse_alto(path)
        ordered_page = order_theatre_page(parsed_page) if conversion.theatre else order_page(parsed_page)
        pages.append(ordered_page)
    title = conversion.title or document_title(pages)

    root = ET.Element(qname("TEI"), nsmap=NSMAP)
    root.append(build_header(title, conversion.metadata))
    text = ET.SubElement(root, qname("text"))
    body = ET.SubElement(text, qname("body"))
    div_parent = body
    if conversion.article:
        # Le mode article manuel enveloppe toute l'entree convertie.
        div_parent = ET.SubElement(body, qname("div"), type="article")
    current_div = ET.SubElement(div_parent, qname("div"))
    context = ConversionContext(
        body=body,
        div_parent=div_parent,
        current_div=current_div,
        theatre=conversion.theatre,
    )

    # Les pages sont ajoutees dans l'ordre, avec un pb avant leurs blocs.
    for page in pages:
        current_div.append(page_break(page))
        for block in page.blocks:
            context.add_block(block)

    return ET.ElementTree(root)


@dataclass
class ConversionContext:
    """Garde l'etat courant pendant la construction du corps TEI.

    :param body: element <body> du document TEI.
    :type body: ET._Element
    :param div_parent: parent direct des divisions de contenu.
    :type div_parent: ET._Element
    :param current_div: division TEI actuellement remplie.
    :type current_div: ET._Element
    :param last_by_label: dernier element cree pour chaque label LADaS.
    :type last_by_label: dict[str, ET._Element]
    :param open_note: note marginale ouverte, si elle existe.
    :type open_note: ET._Element | None
    :param open_list: liste ouverte, si elle existe.
    :type open_list: ET._Element | None
    :param last_text_element: dernier element textuel cree.
    :type last_text_element: ET._Element | None
    :param last_text_block: dernier bloc ALTO textuel traite.
    :type last_text_block: AltoBlock | None
    :param last_article: dernier div article connu.
    :type last_article: ET._Element | None
    :param open_speech: replique <sp> ouverte en mode theatre.
    :type open_speech: ET._Element | None
    :param column_breaks: colonnes deja signalees par milestone.
    :type column_breaks: set[int]
    :param graphic_part_targets: parties graphiques pouvant recevoir un titre.
    :type graphic_part_targets: list[ET._Element]
    :param theatre: active le traitement specifique des pieces de theatre.
    :type theatre: bool

    :return: Objet modifiable utilise pendant la conversion.
    :rtype: ConversionContext
    """

    body: ET._Element
    div_parent: ET._Element
    current_div: ET._Element
    last_by_label: dict[str, ET._Element] = field(default_factory=dict)
    open_note: ET._Element | None = None
    open_list: ET._Element | None = None
    last_text_element: ET._Element | None = None
    last_text_block: AltoBlock | None = None
    last_article: ET._Element | None = None
    open_speech: ET._Element | None = None
    column_breaks: set[int] = field(default_factory=set)
    graphic_part_targets: list[ET._Element] = field(default_factory=list)
    theatre: bool = False

    def add_block(self, block: AltoBlock) -> None:
        """Ajoute un bloc ALTO dans le corps TEI.

        :param block: bloc ALTO ordonne a convertir.
        :type block: AltoBlock

        :return: None; modifie le contexte TEI courant.
        :rtype: None
        """
        # Le mode theatre intercepte certains labels avant le mapping normal.
        if self.theatre and self.add_theatre_block(block):
            return

        # Les numeros de page peuvent etre ajoutes dans le dernier paragraphe.
        if block.label == "NumberingZone":
            numbering = numbering_element(block)
            is_page_number = ET.QName(numbering).localname == "milestone"
            if is_page_number and self.last_text_element is not None:
                self.last_text_element.append(numbering)
            else:
                self.current_div.append(numbering)
            self._reset_inline_containers()
            return

        if is_empty_ignored_block(block):
            return

        spec = LADAS_TO_TEI.get(block.label, TeiElementSpec(("ab",)))
        target = self.last_text_element
        lines = lines_for_output(block)

        # Si le bloc ne continue pas le precedent, on cree une nouvelle cible TEI.
        if not self.should_continue_previous_text(block):
            parent = self.parent_for(block, spec)
            if is_labelled_head_tail(block):
                target = self.target_for_labelled_head(parent, block, spec)
                lines = (block.lines[-1],)
            else:
                target = self.target_for(parent, block, spec)

        self.add_column_milestone(block, target)
        add_lines(target, lines, use_lb=ET.QName(target).localname != "item")
        self.remember_block(block, target)
        if ET.QName(target).localname in {"p", "ab", "quote"}:
            self.last_text_element = target
            self.last_text_block = block

    def add_theatre_block(self, block: AltoBlock) -> bool:
        """Convertit un bloc selon les regles du mode theatre.

        :param block: bloc ALTO a traiter comme locuteur, replique ou didascalie.
        :type block: AltoBlock

        :return: True si le bloc a ete traite par le mode theatre, sinon False.
        :rtype: bool
        """
        # En mode theatre, les titres deviennent des locuteurs.
        if block.label == "RunningTitleZone":
            milestone, running_title = theatre_running_title_elements(block)
            if milestone is not None:
                self.current_div.append(milestone)
            self.current_div.append(running_title)
            self._reset_inline_containers()
            self.open_speech = None
            return True

        if block.label == "MainZone-Head":
            speech = ET.SubElement(self.current_div, qname("sp"))
            speaker = ET.SubElement(speech, qname("speaker"))
            add_lines(speaker, block.lines)
            self.open_speech = speech
            self._reset_text_context()
            self._reset_inline_containers()
            return True

        if block.label == "MainZone-Lg":
            lg = ET.SubElement(self.speech_parent(), qname("lg"))
            add_verse_lines(lg, block.lines)
            self.remember_block(block, lg)
            self._reset_text_context()
            return True

        if block.label == "MainZone-PStyled":
            stage = ET.SubElement(self.speech_parent(), qname("stage"))
            add_lines(stage, block.lines)
            self.remember_block(block, stage)
            self._reset_text_context()
            return True

        if block.label in THEATRE_PARAGRAPH_LABELS:
            paragraph = ET.SubElement(self.speech_parent(), qname("p"), theatre_paragraph_attrs(block.label))
            add_lines(paragraph, block.lines)
            self.remember_block(block, paragraph)
            self.last_text_element = paragraph
            self.last_text_block = block
            return True

        return False

    def speech_parent(self) -> ET._Element:
        """Retourne le parent ou ajouter une replique de theatre.

        :param self: contexte de conversion courant.
        :type self: objet courant

        :return: Element <sp> ouvert, ou current_div si aucune replique n'est ouverte.
        :rtype: ET._Element
        """
        if self.open_speech is not None:
            return self.open_speech
        return self.current_div

    def remember_block(self, block: AltoBlock, element: ET._Element) -> None:
        """Memorise le dernier element TEI cree pour un label.

        :param block: bloc ALTO source.
        :type block: AltoBlock
        :param element: element TEI cree pour ce bloc.
        :type element: ET._Element

        :return: None; met a jour last_by_label.
        :rtype: None
        """
        self.last_by_label[block.label] = element

    def _reset_text_context(self) -> None:
        """Oublie le dernier element textuel.

        :param self: contexte de conversion courant.
        :type self: objet courant

        :return: None; remet last_text_element et last_text_block a None.
        :rtype: None
        """
        self.last_text_element = None
        self.last_text_block = None

    def parent_for(self, block: AltoBlock, spec: TeiElementSpec) -> ET._Element:
        """Choisit le parent TEI dans lequel inserer le bloc.

        :param block: bloc ALTO a inserer.
        :type block: AltoBlock
        :param spec: mapping TEI associe au label du bloc.
        :type spec: TeiElementSpec

        :return: Element TEI parent a utiliser.
        :rtype: ET._Element
        """
        # Les notes marginales successives restent dans la meme note.
        if block.label.startswith("MarginTextZone-") and spec.wrapper_path == ("note",):
            if self.open_note is None:
                self.open_note = ET.SubElement(self.current_div, qname("note"))
            self.open_list = None
            return self.open_note

        if block.label not in {"MarginTextZone-P", "MarginTextZone-PLabelled", "MarginTextZone-PStructured"}:
            self.open_note = None

        cumulative_parent = self.cumulative_parent(block.label)
        if cumulative_parent is not None:
            return cumulative_parent

        if block.label == "MainZone-Head" and self.can_merge_head(block):
            return self.current_div

        # Les items consecutifs partagent la meme liste.
        if block.label == "MainZone-Item":
            if self.open_list is None:
                numbering = item_numbering(block)
                if numbering:
                    ET.SubElement(self.current_div, qname("fw"), type="numbering").text = numbering
                self.open_list = ET.SubElement(self.current_div, qname("list"))
            return self.open_list
        self.open_list = None

        # Un nouveau titre principal ouvre une nouvelle division si la precedente contient deja du texte.
        if block.label == "MainZone-Head" and div_has_section_content(self.current_div):
            self.current_div = ET.SubElement(self.div_parent, qname("div"))
        elif block.label in {"Article", "Article-MultipleCol"}:
            if self.current_div.get("type") == "article" and self.current_div.getparent() is not None:
                self.current_div = self.current_div.getparent()
            self.current_div = ET.SubElement(self.current_div, qname("div"), dict(spec.attrs))
            self.last_article = self.current_div
            return self.current_div
        elif block.label == "Article-Continued":
            article = nearest_article(self.current_div)
            if article is not None:
                self.last_article = article
                return article
            if self.last_article is not None:
                self.current_div = self.last_article
                return self.last_article
            self.current_div = ET.SubElement(self.current_div, qname("div"), dict(spec.attrs))
            self.last_article = self.current_div
            return self.current_div

        return self.current_div

    def target_for(self, parent: ET._Element, block: AltoBlock, spec: TeiElementSpec) -> ET._Element:
        """Cree ou retrouve l'element TEI qui recevra le texte du bloc.

        :param parent: element TEI parent.
        :type parent: ET._Element
        :param block: bloc ALTO a convertir.
        :type block: AltoBlock
        :param spec: mapping TEI associe au label du bloc.
        :type spec: TeiElementSpec

        :return: Element TEI cible a remplir.
        :rtype: ET._Element
        """
        # Les conteneurs d'article sont deja crees par parent_for().
        if block.label in {"Article", "Article-Continued", "Article-MultipleCol"}:
            return parent
        if block.label == "MainZone-Head" and self.can_merge_head(block):
            return self.current_div[-1]

        # Un titre de partie graphique va dans la premiere partie encore sans titre.
        if block.label == "GraphicZone-Head":
            graphic_part = self.next_graphic_part_without_head()
            if graphic_part is not None:
                return ET.SubElement(graphic_part, qname("head"), dict(spec.attrs))
        if block.label == "MainZone-Item":
            return ET.SubElement(parent, qname("item"))
        if block.label == "DigitizationArtefactZone" and self.last_text_element is not None:
            return ET.SubElement(self.last_text_element, qname("fw"), dict(spec.attrs))
        target_parent = parent
        if spec.wrapper_path and spec.wrapper_path != ("note",):
            for tag in spec.wrapper_path:
                target_parent = ET.SubElement(target_parent, qname(tag))
        for depth, tag in enumerate(spec.path):
            attrs = dict(spec.attrs) if depth == 0 else {}
            target_parent = ET.SubElement(target_parent, qname(tag), attrs)
        if block.label == "GraphicZone-Part":
            self.graphic_part_targets.append(target_parent)
        return target_parent

    def target_for_labelled_head(
        self,
        parent: ET._Element,
        block: AltoBlock,
        spec: TeiElementSpec,
    ) -> ET._Element:
        """Separe un titre dont la derniere ligne est une etiquette.

        :param parent: element TEI parent.
        :type parent: ET._Element
        :param block: bloc MainZone-Head contenant titre et etiquette.
        :type block: AltoBlock
        :param spec: mapping TEI du titre.
        :type spec: TeiElementSpec

        :return: Paragraphe TEI qui recevra la ligne d'etiquette.
        :rtype: ET._Element
        """
        head = ET.SubElement(parent, qname("head"), dict(spec.attrs))
        add_lines(head, block.lines[:-1])
        labelled = ET.SubElement(parent, qname("p"), rend="labelled")
        self.last_text_element = labelled
        return labelled

    def add_column_milestone(self, block: AltoBlock, target: ET._Element) -> None:
        """Ajoute un jalon de colonne au debut d'une nouvelle colonne.

        :param block: bloc ALTO avec colonne detectee.
        :type block: AltoBlock
        :param target: element TEI dans lequel ajouter le jalon.
        :type target: ET._Element

        :return: None; ajoute un milestone si necessaire.
        :rtype: None
        """
        if block.column is None or block.column in self.column_breaks:
            return
        if ET.QName(target).localname not in {"p", "ab", "quote"}:
            return
        target.append(ET.Element(qname("milestone"), unit="column", n=str(block.column)))
        self.column_breaks.add(block.column)

    def can_merge_head(self, block: AltoBlock) -> bool:
        """Verifie si un titre doit prolonger le titre precedent.

        :param block: bloc ALTO courant.
        :type block: AltoBlock

        :return: True si le titre peut etre fusionne avec le titre precedent.
        :rtype: bool
        """
        if block.label != "MainZone-Head" or len(self.current_div) == 0:
            return False
        return ET.QName(self.current_div[-1]).localname == "head" and not div_has_section_content(self.current_div)

    def should_continue_previous_text(self, block: AltoBlock) -> bool:
        """Decide si un bloc continue le dernier element textuel.

        :param block: bloc ALTO courant.
        :type block: AltoBlock

        :return: True si le texte doit etre ajoute au paragraphe precedent.
        :rtype: bool
        """
        if self.last_text_element is None:
            return False
        if block.label == "MainZone-Continued":
            return True
        if block.label != "MainZone-P" or self.last_text_block is None:
            return False
        if block.column is not None:
            return False
        if self.last_text_block.label != "MainZone-P" or block.column != self.last_text_block.column:
            return False
        if block.vpos is None or self.last_text_block.vpos is None:
            return False
        return 0 < block.vpos - self.last_text_block.vpos < 55

    def next_graphic_part_without_head(self) -> ET._Element | None:
        """Trouve la prochaine partie graphique sans titre.

        :param self: contexte de conversion courant.
        :type self: objet courant

        :return: Element graphique sans <head>, ou None.
        :rtype: ET._Element | None
        """
        for part in self.graphic_part_targets:
            if not part.xpath("./tei:head", namespaces={"tei": TEI_NS}):
                return part
        return None

    def cumulative_parent(self, label: str) -> ET._Element | None:
        """Retrouve le dernier parent compatible avec un label cumulatif.

        :param label: label LADaS du bloc courant.
        :type label: str

        :return: Element TEI parent trouve, ou None.
        :rtype: ET._Element | None
        """
        parent_labels = CUMULATIVE_PARENT_LABELS.get(label)
        if not parent_labels:
            return None
        for previous_label in reversed(list(self.last_by_label)):
            if previous_label in parent_labels:
                return self.last_by_label[previous_label]
        return None

    def _reset_inline_containers(self) -> None:
        """Ferme les conteneurs inline gardes en memoire.

        :param self: contexte de conversion courant.
        :type self: objet courant

        :return: None; remet open_note et open_list a None.
        :rtype: None
        """
        self.open_note = None
        self.open_list = None


def nearest_article(element: ET._Element) -> ET._Element | None:
    """Remonte l'arbre TEI jusqu'au div article le plus proche.

    :param element: element TEI de depart.
    :type element: ET._Element

    :return: Element div type="article" le plus proche, ou None.
    :rtype: ET._Element | None
    """
    current = element
    while current is not None:
        if ET.QName(current).localname == "div" and current.get("type") == "article":
            return current
        current = current.getparent()
    return None


def div_has_section_content(div: ET._Element) -> bool:
    """Verifie si une division contient deja du contenu principal.

    :param div: element TEI <div> a inspecter.
    :type div: ET._Element

    :return: True si la division contient un paragraphe, une liste ou un bloc proche.
    :rtype: bool
    """
    section_tags = {"p", "ab", "address", "quote", "lg", "list", "signed", "dateline"}
    for child in div:
        if ET.QName(child).localname in section_tags:
            return True
    return False


def lines_for_output(block: AltoBlock) -> tuple[str, ...]:
    """Prepare les lignes a ecrire dans le TEI.

    :param block: bloc ALTO source.
    :type block: AltoBlock

    :return: Lignes OCR a ecrire, parfois nettoyees ou videes selon le label.
    :rtype: tuple[str, ...]
    """
    if block.label in EMPTY_TEXT_CONTAINER_LABELS:
        return ()
    if block.label == "MainZone-Item":
        return strip_item_numbering(block.lines)
    return block.lines


def is_labelled_head_tail(block: AltoBlock) -> bool:
    """Detecte un titre dont la derniere ligne est une etiquette.

    :param block: bloc ALTO a tester.
    :type block: AltoBlock

    :return: True si le bloc est un MainZone-Head termine par une ligne entre parentheses.
    :rtype: bool
    """
    return bool(
        block.label == "MainZone-Head"
        and block.lines
        and block.lines[-1].lstrip().startswith("(")
    )


THEATRE_PARAGRAPH_LABELS = {
    "MainZone-P",
    "MainZone-PLabelled",
    "MainZone-PQuoted",
    "MainZone-PStructured",
    "MainZone-Continued",
}


def theatre_paragraph_attrs(label: str) -> dict[str, str]:
    """Donne les attributs TEI d'un paragraphe de theatre.

    :param label: label LADaS du paragraphe.
    :type label: str

    :return: Dictionnaire d'attributs XML pour le <p>.
    :rtype: dict[str, str]
    """
    if label == "MainZone-PLabelled":
        return {"rend": "labelled"}
    if label == "MainZone-PQuoted":
        return {"rend": "quoted"}
    if label == "MainZone-PStructured":
        return {"rend": "structured"}
    if label == "MainZone-Continued":
        return {"rend": "continued"}
    return {}


def item_numbering(block: AltoBlock) -> str | None:
    """Extrait la numerotation initiale d'un item.

    :param block: bloc MainZone-Item.
    :type block: AltoBlock

    :return: Numerotation trouvee, ou None.
    :rtype: str | None
    """
    if not block.lines:
        return None
    match = re.match(r"\s*(\d+\s*[—-])\s*(.*)", block.lines[0])
    if not match:
        return None
    return match.group(1).strip()


def strip_item_numbering(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Supprime la numerotation au debut d'un item.

    :param lines: lignes OCR de l'item.
    :type lines: tuple[str, ...]

    :return: Lignes sans numero initial sur la premiere ligne.
    :rtype: tuple[str, ...]
    """
    if not lines:
        return lines
    first = re.sub(r"^\s*\d+\s*[—-]\s*", "", lines[0])
    return (first, *lines[1:])


def add_lines(element: ET._Element, lines: Iterable[str], use_lb: bool = True) -> None:
    """Ajoute des lignes de texte dans un element TEI.

    :param element: element TEI a remplir.
    :type element: ET._Element
    :param lines: lignes de texte a ajouter.
    :type lines: Iterable[str]
    :param use_lb: ajoute un <lb/> avant chaque ligne si True.
    :type use_lb: bool

    :return: None; modifie element en place.
    :rtype: None
    """
    previous = None
    for line in lines:
        if use_lb:
            previous = ET.SubElement(element, qname("lb"))
            previous.tail = line
        elif previous is None:
            element.text = (element.text or "") + line
            previous = element
        else:
            previous.tail = (previous.tail or "") + " " + line


def add_verse_lines(element: ET._Element, lines: Iterable[str]) -> None:
    """Ajoute des vers dans un groupe de vers.

    :param element: element TEI <lg>.
    :type element: ET._Element
    :param lines: lignes OCR a convertir en vers.
    :type lines: Iterable[str]

    :return: None; ajoute un <l> par ligne.
    :rtype: None
    """
    for line in lines:
        verse = ET.SubElement(element, qname("l"))
        lb = ET.SubElement(verse, qname("lb"))
        lb.tail = line


def theatre_running_title_elements(block: AltoBlock) -> tuple[ET._Element | None, ET._Element]:
    """Separe le numero de page du titre courant en mode theatre.

    :param block: bloc RunningTitleZone de theatre.
    :type block: AltoBlock

    :return: Tuple avec milestone de page optionnel et element <fw>.
    :rtype: tuple[ET._Element | None, ET._Element]
    """
    lines = list(block.lines)
    first_line = lines[0] if lines else ""
    match = re.match(r"\s*(\d+)\s+(.+)", first_line)
    milestone = None
    if match:
        milestone = ET.Element(qname("milestone"), unit="page", n=match.group(1))
        lines[0] = match.group(2)
    running_title = ET.Element(qname("fw"), type="runningTitle")
    add_lines(running_title, lines, use_lb=False)
    return milestone, running_title


def numbering_element(block: AltoBlock) -> ET._Element:
    """Convertit un bloc de numerotation en TEI.

    :param block: bloc ALTO NumberingZone.
    :type block: AltoBlock

    :return: Element milestone si c'est un numero de page, sinon element <fw>.
    :rtype: ET._Element
    """
    text = block.text
    page_number = re.search(r"\d+", text or "")
    if page_number and re.fullmatch(r"[\W_]*\d+[\W_]*", text):
        return ET.Element(qname("milestone"), unit="page", n=page_number.group())
    fw = ET.Element(qname("fw"), type="numbering")
    add_lines(fw, block.lines, use_lb=False)
    return fw


def page_break(page: AltoPage) -> ET._Element:
    """Cree un saut de page TEI.

    :param page: page ALTO source.
    :type page: AltoPage

    :return: Element TEI <pb> avec attribut facs.
    :rtype: ET._Element
    """
    pb = ET.Element(qname("pb"))
    pb.set("facs", page.source.name)
    return pb


def build_header(title: str, metadata: dict[str, str]) -> ET._Element:
    """Construit l'en-tete TEI minimal.

    :param title: titre par defaut du document.
    :type title: str
    :param metadata: metadonnees selectionnees depuis le CSV.
    :type metadata: dict[str, str]

    :return: Element TEI <teiHeader>.
    :rtype: ET._Element
    """
    header = ET.Element(qname("teiHeader"))
    file_desc = ET.SubElement(header, qname("fileDesc"))
    title_stmt = ET.SubElement(file_desc, qname("titleStmt"))
    ET.SubElement(title_stmt, qname("title")).text = metadata.get("title", title)
    if metadata.get("author"):
        ET.SubElement(title_stmt, qname("author")).text = metadata["author"]
    resp_stmt = ET.SubElement(title_stmt, qname("respStmt"))
    resp_stmt.set(f"{{{XML_NS}}}id", "resp1")
    ET.SubElement(resp_stmt, qname("resp")).text = "Encoding"
    ET.SubElement(resp_stmt, qname("persName")).text = metadata.get("encoder", "Juliette Janes")
    publication_stmt = ET.SubElement(file_desc, qname("publicationStmt"))
    if metadata.get("publisher"):
        ET.SubElement(publication_stmt, qname("publisher")).text = metadata["publisher"]
    if metadata.get("date"):
        ET.SubElement(publication_stmt, qname("date"), when=metadata["date"]).text = metadata["date"]
    ET.SubElement(publication_stmt, qname("p")).text = metadata.get(
        "publication", "Generated from LADaS-annotated ALTO"
    )
    source_desc = ET.SubElement(file_desc, qname("sourceDesc"))
    ET.SubElement(source_desc, qname("p")).text = metadata.get("source", "LADaS")
    revision = ET.SubElement(header, qname("revisionDesc"))
    change = ET.SubElement(revision, qname("change"), when=str(date.today()), who="#resp1")
    change.text = "Generation du XML TEI depuis ALTO annote LADaS"
    return header


def document_title(pages: Sequence[AltoPage]) -> str:
    """Deduit un titre depuis les pages ALTO.

    :param pages: pages ALTO deja lues.
    :type pages: Sequence[AltoPage]

    :return: Titre tire du premier nom de fichier, ou ladas2tei.
    :rtype: str
    """
    if not pages:
        return "ladas2tei"
    first = pages[0].source.stem
    return re.sub(r"_f?\d+$", "", first) or first


def write_tei(tree: ET._ElementTree, output: str | Path) -> None:
    """Ecrit un arbre TEI sur disque.

    :param tree: arbre XML TEI a serialiser.
    :type tree: ET._ElementTree
    :param output: chemin du fichier XML de sortie.
    :type output: str | Path

    :return: None; cree les dossiers parents et ecrit le fichier.
    :rtype: None
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="UTF-8", xml_declaration=True, pretty_print=True)
