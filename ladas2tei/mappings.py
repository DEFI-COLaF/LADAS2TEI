from __future__ import annotations

from ladas2tei.models import TeiElementSpec


LADAS_TO_TEI: dict[str, TeiElementSpec] = {
    # Zones principales
    "DamageZone": TeiElementSpec(("damage",)),
    "DigitizationArtefactZone": TeiElementSpec(("fw",), (("type", "digitisation-artefact"),)),
    "FigureZone": TeiElementSpec(("figure",)),
    "FormZone": TeiElementSpec(("figure",), (("type", "form"),)),
    "GraphicZone": TeiElementSpec(("figure",)),
    "GraphicZone-Decoration": TeiElementSpec(("figure",), (("type", "decoration"),)),
    "MusicZone": TeiElementSpec(("notatedMusic",)),
    "QuireMarksZone": TeiElementSpec(("fw",), (("type", "quiremarks"),)),
    "RunningTitleZone": TeiElementSpec(("fw",), (("type", "runningTitle"),)),
    "SealZone": TeiElementSpec(("stamp",), (("type", "seal"),)),
    "StampZone": TeiElementSpec(("stamp",)),
    "TableZone": TeiElementSpec(("figure",), (("type", "table"),)),
    "TitlePageZone": TeiElementSpec(("div",), (("type", "titlePage"),)),
    # Zones du texte principal
    "DropCapitalZone": TeiElementSpec(("hi",), (("rend", "drop-capital"),)),
    "MainZone-DropCapital": TeiElementSpec(("hi",), (("rend", "drop-capital"),)),
    "MainZone-Ab": TeiElementSpec(("ab",)),
    "MainZone-Address": TeiElementSpec(("address",)),
    "MainZone-Continued": TeiElementSpec(("ab",), (("rend", "continued"),)),
    "MainZone-Date": TeiElementSpec(("dateline",)),
    "MainZone-Dateline": TeiElementSpec(("dateline",)),
    "MainZone-Head": TeiElementSpec(("head",)),
    "MainZone-HeadStructured": TeiElementSpec(("head",), (("type", "structured"),)),
    "MainZone-Item": TeiElementSpec(("item",), wrapper_path=("list",)),
    "MainZone-Lg": TeiElementSpec(("lg",)),
    "MainZone-Maths": TeiElementSpec(("figure", "formula"), (("type", "maths"),)),
    "MainZone-P": TeiElementSpec(("p",)),
    "MainZone-PLabelled": TeiElementSpec(("p",), (("rend", "labelled"),)),
    "MainZone-PQuoted": TeiElementSpec(("quote",)),
    "MainZone-PStructured": TeiElementSpec(("p",), (("rend", "structured"),)),
    "MainZone-PStyled": TeiElementSpec(("p",), (("rend", "styled"),)),
    "MainZone-Signed": TeiElementSpec(("signed",)),
    # Zones internes aux graphiques, figures, formulaires et tableaux
    "FigureZone-Head": TeiElementSpec(("head",)),
    "FormZone-Field": TeiElementSpec(("cell",)),
    "FormZone-Head": TeiElementSpec(("head",)),
    "FormZone-Part": TeiElementSpec(("div",)),
    "GraphicZone-Ab": TeiElementSpec(("ab",)),
    "GraphicZone-Head": TeiElementSpec(("head",)),
    "GraphicZone-P": TeiElementSpec(("p",)),
    "GraphicZone-Part": TeiElementSpec(("figure",)),
    "TableZone-Head": TeiElementSpec(("head",)),
    "TableZone-P": TeiElementSpec(("p",)),
    # Zones marginales
    "MarginTextZone": TeiElementSpec(("note",)),
    "MarginTextZone-Ab": TeiElementSpec(("ab",), wrapper_path=("note",)),
    "MarginTextZone-Continued": TeiElementSpec(("note",), (("rend", "continued"),)),
    "MarginTextZone-ContinuedNotes": TeiElementSpec(("note",), (("rend", "continued"),)),
    "MarginTextZone-Lg": TeiElementSpec(("lg",), wrapper_path=("note",)),
    "MarginTextZone-ManuscriptAddendum": TeiElementSpec(("note",), (("type", "handwritten"),)),
    "MarginTextZone-P": TeiElementSpec(("p",), wrapper_path=("note",)),
    "MarginTextZone-PLabelled": TeiElementSpec(("p",), (("rend", "labelled"),), wrapper_path=("note",)),
    "MarginTextZone-PStructured": TeiElementSpec(("p",), (("rend", "structured"),), wrapper_path=("note",)),
    "MarginTextZone-PStyled": TeiElementSpec(("p",), (("rend", "styled"),), wrapper_path=("note",)),
    # Labels d'articles de presse observes dans les exemples.
    "Article": TeiElementSpec(("div",), (("type", "article"),)),
    "Article-Continued": TeiElementSpec(("div",), (("type", "article"),)),
    "Article-MultipleCol": TeiElementSpec(("div",), (("type", "article"),)),
    "HeadArt-MultipleCol": TeiElementSpec(("head",)),
}


CUMULATIVE_PARENT_LABELS = {
    "FigureZone-Head": {"FigureZone"},
    "FormZone-Field": {"FormZone"},
    "FormZone-Head": {"FormZone"},
    "FormZone-Part": {"FormZone"},
    "GraphicZone-Ab": {"GraphicZone", "GraphicZone-Part"},
    "GraphicZone-Head": {"GraphicZone", "GraphicZone-Part"},
    "GraphicZone-P": {"GraphicZone", "GraphicZone-Part"},
    "GraphicZone-Part": {"GraphicZone"},
    "TableZone-Head": {"TableZone"},
    "TableZone-P": {"TableZone"},
}


EMPTY_TEXT_CONTAINER_LABELS = {
    "FigureZone",
    "FormZone",
    "GraphicZone",
    "GraphicZone-Decoration",
    "GraphicZone-Part",
    "TableZone",
}
