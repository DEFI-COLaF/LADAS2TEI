import os
import click
from lxml import etree as ET
from datetime import datetime
import csv
import re
import pkg_resources
import json

tei_mapping = {
    "Division": {"tag":"div"},
    "PageTitleZone": {"tag":"div", "att":{"type":"titlepage"}, "nested":{"tag":"p"}},
    "MainZone-P": {"tag":"p"},
    "MainZone-Sp":{"tag":"sp"},
    "MainZone-Head":{"tag":"head"},
    "MainZone-Lg":{"tag":"lg"},
    "MainZone-Other":{"tag":"div", "att":{"type":"other"}},
    "NumberingZone": {"tag":"fw","att":{"type":"numbering"}},
    "MarginTextZone-ManuscriptAddedum":{"tag":"fw", "att":{"type":"margin"}},
    "MarginTextZone":{"tag":"note"},
    "GraphicZone-Decoration": {"tag":"figure","att":{"type":"decoration"}},

}
cumulative = {
        "GraphicZone-FigDesc": "GraphicZone",
        "GraphicZone-Head": "GraphicZone",
        "GraphicZone-Part": "GraphicZone",
        "GraphicZone-TextualContent": "GraphicZone",
        "FigureZone-FigDesc" : "FigureZone",
        "FigureZone-Head":"FigureZone",
        "TableZone-Head": "TableZone",
    } 


def process_document(directory, doc, dict_block, n,n_zone, n_div):
    """
    Processes each document in the directory, applies XSLT, and generates the corresponding TEI structure.
    
    :param doc: The document to be processed.
    :param directory: Directory containing the XML files.
    """
    transformed_tree = apply_xslt(directory+'/'+doc)
    if transformed_tree:
        root = transformed_tree.getroot()
        liste_zone = root.findall('region')
        n_interne = 0
        for zone in liste_zone:
            n_zone+=1
            n_interne+=1
            zone_type = zone.attrib.get('type', None)
            tag = tei_mapping.get(zone_type, '<ab>')
            continued = "Continued" in zone_type if zone_type else False
            cumul = cumulative.get(zone_type, False) if zone_type else False
            is_list = True if isinstance(tag, list) else False
            liste_line = process_line(zone, tag)
            if zone_type == "PageTitleZone":
                if 'PageTitleZone' in dict_block.keys():
                    dict_block[zone_type] = dict_block[f'{zone_type}']+liste_line
                else:
                    dict_block[zone_type] = liste_line
            else:
                if n_div>0:
                    last_key = list(dict_block[f'Division-{n_div}'].keys())[-1]
                if zone_type =='MainZone-Head' and n_div>0 and 'MainZone-Head' not in last_key:
                    n_div +=1
                    dict_block[f'Division-{n_div}'] = {}
                    dict_block[f'Division-{n_div}'][f'{zone_type}-{n_zone}']=liste_line
                elif zone_type=='MainZone-P-Continued' and 'MainZone-P' in last_key:
                    dict_block[f'Division-{n_div}'][last_key] = dict_block[f'Division-{n_div}'][last_key]+liste_line
                elif f'Division-{n_div}' in dict_block.keys():
                    dict_block[f'Division-{n_div}'][f'{zone_type}-{n_zone}']=liste_line
                else:
                    n_div +=1
                    dict_block[f'Division-{n_div}'] = {}
                    dict_block[f'Division-{n_div}'][f'{zone_type}-{n_zone}']=liste_line
            if n_interne ==1:
                # si il s'agit de la 1ere zone de la page, ajouter l'élément page break en 1ere position de la liste
                last_key_first_level = list(dict_block.keys())[-1]
                if isinstance(dict_block[last_key_first_level], dict):
                    last_key_second_level = list(dict_block[last_key_first_level].keys())[-1]
                    dict_block[last_key_first_level][last_key_second_level].insert(0,(n, doc.replace("xml","jpg")))
                else:
                    dict_block[last_key_first_level].insert(0,(n, doc.replace("xml","jpg")))
    return dict_block,n_zone, n_div


def fill_header(template_file, metadata):
    with open(template_file, 'r', encoding='utf-8') as file:
        template = file.read()
    placeholders = re.findall(r'\[(\w+)\]', template)
    replacements = { column: metadata.get(column, '') for column in placeholders}
    replacements['date_today'] = datetime.today().date()
    for placeholder, value in replacements.items():
        template = template.replace(f'[{placeholder}]', str(value))
    return template


def apply_xslt(xml_file):
    """
    Parses an XML file and applies an XSLT transformation.
    
    :param xml_file: Path to the input XML file.
    :type xml_file: str
    :return: Transformed XML tree or None in case of error.
    :rtype: ElementTree
    """
    xslt_file = "ladas2tei/alto2XMLsimple.xsl"
    try:
        xml_tree = ET.parse(xml_file)
        xslt_tree = ET.parse(xslt_file)
        transform = ET.XSLT(xslt_tree)
        return transform(xml_tree)
    except Exception as e:
        print(f"Error: {e}")
        return None


def process_line(zone, tag):
    """
    Convert the text contained in an ALTO zone into a list of line, 
    removing the line with too much noise

    :param zone: ALTO simplified zone
    :type zone: ElementTree
    :param tag: Zone type
    :type tag: str
    :return: lines without noise
    :rtype: list of str
    """
    liste_line = []
    n_line=0
    for line in zone.findall("line"):
        n_line +=1
        text = line.text
        if text:
            # calcul du nombre de caractères alphabétiques dans la ligne
            numeric_char = [char for char in text if char.isalpha()]
            # Si la moitié des caractères de la ligne ne sont pas alphabétiques et qu'il ne 
            # s'agit pas de zones contenant normalement beaucoup de nombres, passer.
            if len(numeric_char)/len(text)<0.5 and tag not in ["NumberingZone", "QuiremarkZone"]:
                pass
            else:
                text = text.replace("&", "et")
                liste_line.append(text)
    return liste_line


def add_tei_line(liste_line, parent):
    """
    Add the textual content of the blocks to the corresponding ElementTree.

    :param liste_line: list of lines, textual content of the block
    :type liste_line: list of str
    :param parent: TEI parent block of the lines
    :type parent: ElementTree
    :return: TEI parent block with the textual content in the form <lb/>line
    :rtype: ElementTree
    """
    n_line=0
    for line in liste_line:
        if isinstance(line, tuple):
            n, doc = line
            pb = ET.Element('pb', n=str(n), facs=doc)
            parent.append(pb)
        else:
            n_line+=1
            # création d'un élément XML lb et ajout comme enfant de l'élément parent
            lb = ET.Element('lb', n=str(n_line))
            parent.append(lb)
            # ajout à la suite du lb du texte de la ligne
            lb.tail = line


def dict2tei(dict_block, body_xml):
    """
    Convert the nested dictionary into a xml body

    :param dict_block: nested dictionary {tag:[text]} for the all document
    :type dict_block: dict of dict with list of str value
    :param body_xml: TEI parent block
    :type body_xml: ElementTree
    :return: body with zones and lines completed
    :rtype: ElementTree
    """
    for key,value in dict_block.items():
        # récupérer le dictionnaire du tag dans le dictionnaire de mapping, si pas de tag ab
        clean_key = re.sub(r'-\d+','',key)
        element_info = tei_mapping.get(clean_key, "ab")
        if element_info!='ab':
            # récupérer les dif info sur le tag
            tag = element_info.get("tag")
            attributes=element_info.get("att")
            nested = element_info.get("nested")
        
        # si l'élément traité a des enfants
        if isinstance(value, dict):
            # créer la balise xml du enfant
            child = ET.SubElement(body_xml, tag, attributes)
            # pour chaque key du sous dictionnaire
            for subkey, subvalue in value.items():
                # nettoyer le numéro et récupérer le tag de l'élément enfant
                clean_key = re.sub(r'-\d+','',subkey)
                sub_element_info = tei_mapping.get(clean_key, "ab")
                if sub_element_info!="ab":
                    tag = sub_element_info.get("tag")
                    attributes=sub_element_info.get("att")
                    nested = sub_element_info.get("nested")
                else:
                    tag=sub_element_info
                    attributes = None
                # créer la balise xml petit-enfant et ajouter le contenu textuel
                grandchild = ET.SubElement(child,tag,attrib=attributes)
                add_tei_line(subvalue, grandchild)
        # si l'élément traité n'a pas d'enfants
        elif isinstance(value, list):
            # créer la balise enfant
            child = ET.SubElement(body_xml,tag, attrib=attributes)
            # si le tag est un tag nested (par exemple Titlepage prend une div puis un p avant le contenu textuel)
            if nested:
                p_element = ET.SubElement(child, "p")
                add_tei_line(value, p_element)
            else:
                add_tei_line(value, child)
                    
            
    
@click.command()
@click.argument('csv_metadata', type=str)
@click.argument('pattern_header', type=str, required=False)
def main(csv_metadata, pattern_header):
    if not os.path.exists('TEI'):
        os.makedirs('TEI')
    #xslt_file = pkg_resources.resource_filename("ladas2tei", "alto2XMLsimple.xsl")
    with open(csv_metadata, newline='', encoding="utf-8") as csv_file:
        reader=csv.DictReader(csv_file)

        for row in reader:
            print(f'Traitement de {row["file_name"]}')
            root_xml = ET.Element("TEI", xmlns="http://www.tei-c.org/ns/1.0")

            # Créaton du TEI header
            if pattern_header:
                tei_header = fill_header(pattern_header, row)
            else:
                #tei_header_path = pkg_resources.resource_filename("ladas2tei", "basic_header.txt")
                tei_header_path = "ladas2tei/basic_header.txt"
                tei_header = fill_header(tei_header_path, row)
            root_xml.append(ET.fromstring(tei_header))

            # Création  du corps du text en TEI
            dict_block={}
            n = 0
            n_zone=0
            n_div=0
            for xml_file in sorted(os.listdir(row["file_name"])):
                if 'xml' in xml_file and 'METS' not in xml_file:
                    n+=1
                    dict_block,n_zone,n_div= process_document(row['file_name'], xml_file, dict_block, n,n_zone,n_div)
            
            text_xml = ET.SubElement(root_xml, "text")
            body_xml = ET.SubElement(text_xml, "body")
            dict2tei(dict_block, body_xml)
                   
            output=os.path.basename(row["file_name"])
            with open(f'TEI/{output}.json','w') as f:
                json.dump(dict_block, f)
            with open(f'TEI/{output}.xml', "w") as f:
                f.write(ET.tostring(root_xml, encoding='unicode', pretty_print=True))
        
if __name__ == "__main__":
    main()