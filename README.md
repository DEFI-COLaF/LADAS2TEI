# LADAS2TEI
This Python script transforms XML ALTO files, using LADAS layout analysis descriptions, into TEI files.

Basic Command:
`python ladas2tei.py [csv_file].csv`

The script uses a default TEI header (provided in `basic_header.txt`). The metadata for each TEI file must be included in the CSV file.

To use a custom header, create a header pattern in a text file similar to the one in `pattern_colaf.txt`. You can include your own metadata fields in the CSV by placing their names in brackets in the pattern.
