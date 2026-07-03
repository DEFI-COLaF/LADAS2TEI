# LADAS2TEI

Conversion de fichiers ALTO XML annotes avec les labels LADaS vers un fichier
TEI XML.

Le programme lit les zones ALTO, les remet dans un ordre de lecture, puis cree
le TEI avec `lxml`. 

## Utilisation

Depuis le dossier du projet :

```bash
venv/bin/python -m ladas2tei.main fichier_alto.xml -o sortie.xml --title "Mon titre"
```

Plusieurs pages dans un meme TEI :

```bash
venv/bin/python -m ladas2tei.main page_001.xml page_002.xml page_003.xml -o document.xml --title "Document"
```

Un dossier contenant des XML :

```bash
venv/bin/python -m ladas2tei.main dossier_alto -o document.xml --title "Document"
```

### Mode article

```bash
venv/bin/python -m ladas2tei.main dossier_alto -o article.xml --title "Article" --article
```

### Mode theatre

```bash
venv/bin/python -m ladas2tei.main dossier_alto -o theatre.xml --title "Piece" --theatre
```

### Metadonnees CSV

```bash
venv/bin/python -m ladas2tei.main dossier_alto -o document.xml --metadata-csv metadata.csv
```

Colonnes utiles dans le CSV :

- `title`
- `author`
- `encoder`
- `publisher`
- `date`
- `publication`
- `source`

### Dossier parent

Si l'entree est un dossier qui contient plusieurs sous-dossiers, le script cree
un TEI par sous-dossier. Dans ce cas, `--metadata-csv` est obligatoire.

```bash
venv/bin/python -m ladas2tei.main corpus_parent -o TEI --metadata-csv metadata.csv
```

Structure attendue :

```text
corpus_parent/
  doc_1/
    alto/
      page_001.xml
      page_002.xml
  doc_2/
    alto/
      page_001.xml
metadata.csv
```

Sortie :

```text
TEI/
  doc_1.xml
  doc_2.xml
```

Si `-o` n'est pas donne, le dossier de sortie s'appelle `TEI` et il est cree
dans le dossier parent.

## Organisation

| Fichier | Role |
| --- | --- |
| `ladas2tei/main.py` | Commande, options et choix du mode de conversion |
| `ladas2tei/alto.py` | Lecture ALTO, recuperation du texte et tri des fichiers |
| `ladas2tei/ordering.py` | Ordre de lecture des blocs dans une page |
| `ladas2tei/tei.py` | Construction du TEI |
| `ladas2tei/mappings.py` | Correspondances entre labels LADaS et elements TEI |
| `ladas2tei/models.py` | Création des classes|
| `ladas2tei/metadata.py` |Traitement des métadonnées|
| `ladas2tei/constantes.py` | Namespaces XML |
| `tests/test_converter.py` | Tests de regression |

## Deroulement d'une conversion

1. `main.py` lit les chemins donnes dans la commande.
2. `alto.py` trouve les fichiers XML et les trie dans l'ordre naturel.
3. `parse_alto()` transforme chaque page en blocs `AltoBlock`.
4. `ordering.py` replace les blocs selon les coordonnees et les colonnes.
5. `tei.py` cree l'arbre TEI.
6. `write_tei()` ecrit le fichier final.
