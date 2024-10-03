# LADAS2TEI
Python script that transforms XML ALTO files using LADAS layout analysis description into TEI files.

Basic Command: 'python ladas2tei.py [csv_file].csv'<br/>
It will use a basic tei header (shown in basic_header.txt).The metadata for each tei files needs to be in the csv file.<br/>
To use your own header, create a pattern header in a txt such as the one in the pattern_colaf file. You can use your own metadata field in the csv, you just need to put its name in brackets in the pattern.
