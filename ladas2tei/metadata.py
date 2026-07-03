from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence


def load_metadata(csv_path: str | Path | None) -> list[dict[str, str]]:
    """Charge les metadonnees depuis un CSV.

    :param csv_path: chemin du CSV, ou None.
    :type csv_path: str | Path | None

    :return: Liste de lignes sous forme de dictionnaires.
    :rtype: list[dict[str, str]]
    """
    if not csv_path:
        return []
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle)]


def select_metadata(rows: Sequence[dict[str, str]], alto_files: Sequence[str | Path]) -> dict[str, str]:
    """Choisit la ligne de metadonnees qui correspond aux ALTO.

    :param rows: lignes chargees depuis le CSV.
    :type rows: Sequence[dict[str, str]]
    :param alto_files: fichiers ALTO du document.
    :type alto_files: Sequence[str | Path]

    :return: Ligne de metadonnees trouvee, ou dictionnaire vide.
    :rtype: dict[str, str]
    """
    if not rows:
        return {}
    candidates = metadata_candidates(alto_files)
    for row in rows:
        row_keys = metadata_row_keys(row)
        has_matching_key = any(
            metadata_keys_match(candidate, row_key)
            for candidate in candidates
            for row_key in row_keys
        )
        if has_matching_key:
            return row
    return {}


def metadata_candidates(alto_files: Sequence[str | Path]) -> set[str]:
    """Prepare les cles possibles pour reconnaitre un document.

    :param alto_files: fichiers ALTO du document.
    :type alto_files: Sequence[str | Path]

    :return: Cles normalisees tirees des fichiers et dossiers parents.
    :rtype: set[str]
    """
    candidates: set[str] = set()
    for alto_file in alto_files:
        path = Path(alto_file)
        for candidate in (path, *path.parents):
            candidates.add(normalize_metadata_key(candidate))
    return {candidate for candidate in candidates if candidate}


def metadata_row_keys(row: dict[str, str]) -> set[str]:
    """Extrait les colonnes utilisables comme identifiants.

    :param row: ligne du CSV de metadonnees.
    :type row: dict[str, str]

    :return: Cles normalisees trouvees dans la ligne.
    :rtype: set[str]
    """
    keys: set[str] = set()
    for column in ("id", "file_name", "filename", "name", "title"):
        value = row.get(column)
        if value:
            keys.add(normalize_metadata_key(value))
    return keys


def normalize_metadata_key(value: str | Path) -> str:
    """Normalise une valeur pour comparer fichiers et lignes CSV.

    :param value: chemin ou chaine a comparer.
    :type value: str | Path

    :return: Chaine en minuscules, avec slashs uniformes.
    :rtype: str
    """
    return Path(value).as_posix().rstrip("/").lower()


def metadata_keys_match(left: str, right: str) -> bool:
    """Compare deux cles de metadonnees.

    :param left: premiere cle normalisee.
    :type left: str
    :param right: seconde cle normalisee.
    :type right: str

    :return: True si les cles sont egales ou si l'une termine par l'autre.
    :rtype: bool
    """
    return left == right or left.endswith(f"/{right}") or right.endswith(f"/{left}")
