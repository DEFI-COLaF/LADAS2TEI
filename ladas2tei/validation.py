from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from lxml import etree as ET


DEFAULT_RNG_CANDIDATES = (
    "tei_all.rng",
    "odd_ladas/tei_all.rng",
    "odd_ladas/odd_ladas.rng",
)


@dataclass(frozen=True)
class RngIssue:
    """Erreur signalee par un schema RelaxNG.

    :param line: ligne XML concernee.
    :type line: int
    :param column: colonne XML concernee.
    :type column: int
    :param message: message du validateur.
    :type message: str

    :return: Probleme de validation serialisable dans un rapport.
    :rtype: RngIssue
    """

    line: int
    column: int
    message: str


@dataclass(frozen=True)
class RngValidationResult:
    """Resultat de validation pour un fichier TEI.

    :param file_path: fichier TEI valide.
    :type file_path: Path
    :param valid: True si le fichier est valide.
    :type valid: bool
    :param issues: problemes detectes par le RNG.
    :type issues: tuple[RngIssue, ...]

    :return: Resultat de validation RNG.
    :rtype: RngValidationResult
    """

    file_path: Path
    valid: bool
    issues: tuple[RngIssue, ...]


def resolve_tei_rng_path(rng_path: Path | None) -> Path | None:
    """Trouve le RNG TEI a utiliser.

    :param rng_path: chemin fourni par l'utilisateur, ou None.
    :type rng_path: Path | None

    :return: Chemin RNG trouve, ou None.
    :rtype: Path | None
    """
    if rng_path is not None:
        return rng_path

    roots = (Path.cwd(), Path(__file__).resolve().parent.parent)
    for root in roots:
        for candidate in DEFAULT_RNG_CANDIDATES:
            path = root / candidate
            if path.exists():
                return path
    return None


def validation_report_path(output_path: Path) -> Path:
    """Construit le chemin du rapport RNG.

    :param output_path: fichier ou dossier de sortie TEI.
    :type output_path: Path

    :return: Chemin du rapport texte.
    :rtype: Path
    """
    if output_path.suffix:
        return output_path.with_suffix(".rng.txt")
    return output_path / "tei_rng_report.txt"


def validate_tei_files(
    tei_files: Sequence[Path],
    rng_path: Path,
) -> list[RngValidationResult]:
    """Valide des fichiers TEI avec un schema RNG.

    :param tei_files: fichiers TEI a valider.
    :type tei_files: Sequence[Path]
    :param rng_path: schema RelaxNG.
    :type rng_path: Path

    :return: Resultats de validation, un par fichier.
    :rtype: list[RngValidationResult]
    """
    relaxng = ET.RelaxNG(ET.parse(str(rng_path)))
    results: list[RngValidationResult] = []
    for tei_file in tei_files:
        tree = ET.parse(str(tei_file))
        valid = relaxng.validate(tree)
        issues = tuple(
            RngIssue(entry.line, entry.column, entry.message)
            for entry in relaxng.error_log
            if Path(entry.filename).name in {"", tei_file.name} or entry.filename == str(tei_file)
        )
        results.append(RngValidationResult(tei_file, valid, issues))
    return results


def write_rng_report(
    report_path: Path,
    rng_path: Path | None,
    results: Sequence[RngValidationResult],
) -> None:
    """Ecrit un rapport texte de validation RNG.

    :param report_path: chemin du rapport a creer.
    :type report_path: Path
    :param rng_path: schema RNG utilise, ou None si absent.
    :type rng_path: Path | None
    :param results: resultats de validation.
    :type results: Sequence[RngValidationResult]

    :return: None; ecrit le rapport.
    :rtype: None
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Validation RNG TEI", ""]
    if rng_path is None:
        lines.extend(
            [
                "Schema: introuvable",
                "Aucune validation RNG n'a ete executee.",
                "Place tei_all.rng dans le dossier courant ou passe --tei-rng chemin/tei_all.rng.",
            ]
        )
    else:
        lines.append(f"Schema: {rng_path}")
        lines.append("")
        if not results:
            lines.append("Aucun fichier TEI a valider.")
        for result in results:
            lines.extend(format_result(result))
            lines.append("")

    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def format_result(result: RngValidationResult) -> list[str]:
    """Formate un resultat de validation pour le rapport.

    :param result: resultat d'un fichier.
    :type result: RngValidationResult

    :return: Lignes de rapport.
    :rtype: list[str]
    """
    if result.valid:
        return [f"Fichier: {result.file_path}", "Statut: valide"]

    lines = [
        f"Fichier: {result.file_path}",
        f"Statut: invalide ({len(result.issues)} probleme(s))",
    ]
    for issue in result.issues:
        location = f"ligne {issue.line}, colonne {issue.column}"
        lines.append(f"- {location}: {issue.message}")
    return lines
