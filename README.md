# LADAS2TEI

Conversion de fichiers ALTO XML annotes avec les labels LADaS vers un fichier
TEI XML.

Le programme lit les zones ALTO, les remet dans un ordre de lecture, puis cree
le TEI avec `lxml`. Chaque page ALTO ajoute un changement de page :

```xml
<pb facs="nom_du_fichier.xml"/>
```

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

Ajoute un niveau :

```xml
<div type="article">
```

Commande :

```bash
venv/bin/python -m ladas2tei.main dossier_alto -o article.xml --title "Article" --article
```

### Mode theatre

Le mode theatre sert pour les pieces :

- les locuteurs deviennent des `<speaker>` ;
- les repliques deviennent des `<sp>` ;
- les vers peuvent devenir des `<lg><l>` ;
- les paragraphes restent des `<p>` quand le label le demande ;
- `MainZone-PStyled` devient une didascalie `<stage>`.

Commande :

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

Pour relier une ligne CSV a un dossier, le script regarde notamment :

- `file_name`
- `filename`
- `name`
- `id`
- `title`

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

## Modifier une correspondance LADaS vers TEI

La plupart des modifications se font dans `ladas2tei/mappings.py`.

Exemple simple :

```python
"MainZone-P": TeiElementSpec(("p",)),
```

donne :

```xml
<p>...</p>
```

Avec un attribut :

```python
"MainZone-PStructured": TeiElementSpec(("p",), (("rend", "structured"),)),
```

donne :

```xml
<p rend="structured">...</p>
```

Avec un element imbrique :

```python
"MainZone-Maths": TeiElementSpec(("figure", "formula"), (("type", "maths"),)),
```

donne :

```xml
<figure type="maths">
  <formula>...</formula>
</figure>
```

## Ajouter un label

Pour un nouveau label `MainZone-Subtitle` qui doit devenir :

```xml
<head type="subtitle">...</head>
```

ajouter dans `mappings.py` :

```python
"MainZone-Subtitle": TeiElementSpec(("head",), (("type", "subtitle"),)),
```

## Ajouter un label dans un bloc existant

Certains labels ne creent pas un nouveau bloc. Ils doivent etre ajoutes dans le
bloc precedent.

Exemple :

```python
"GraphicZone-Head": {"GraphicZone", "GraphicZone-Part"},
```

Cela veut dire qu'un `GraphicZone-Head` est ajoute dans la derniere
`GraphicZone` ou `GraphicZone-Part`.

Ces regles sont dans `CUMULATIVE_PARENT_LABELS`, dans `mappings.py`.

## Modifier l'ordre des blocs

L'ordre des blocs est gere dans `ordering.py`.

Fonctions a regarder en premier :

| Fonction | Role |
| --- | --- |
| `order_page()` | Point d'entree pour l'ordre d'une page |
| `order_by_coordinates()` | Tri par coordonnees et colonnes |
| `detect_reading_columns()` | Detection des colonnes |
| `order_theatre_page()` | Ordre specifique au mode theatre |
| `order_article_layout()` | Ordre specifique aux pages d'articles |

Pour une petite correction, commencer par `order_page()`, puis suivre les
fonctions appelees.

## Modifier la lecture ALTO

La lecture se trouve dans `alto.py`.

Fonctions utiles :

| Fonction | Role |
| --- | --- |
| `parse_alto()` | Lit une page ALTO et retourne un `AltoPage` |
| `line_text()` | Lit le texte OCR d'une ligne |
| `expand_alto_inputs()` | Accepte des fichiers ou dossiers et retourne les XML |
| `sort_alto_files()` | Trie les XML |
| `natural_key()` | Place `page_2` avant `page_10` |

Si du texte OCR manque dans le TEI, regarder d'abord `line_text()`.

## Modifier l'en-tete TEI

L'en-tete est cree dans `tei.py`, fonction `build_header()`.

Les valeurs viennent surtout du CSV de metadonnees. Exemple :

```csv
file_name,title,author,date
doc_1,Titre du premier document,Nom auteur,1901
doc_2,Titre du second document,Nom auteur,1902
```

## Tests

Lancer tous les tests :

```bash
venv/bin/python -m unittest discover -s tests -v
```
