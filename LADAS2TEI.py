import os
import click
from lxml import etree as ET
from datetime import datetime
import csv
import re

xslt_file = 'alto2XMLsimple.xsl'
tei_mapping = {
    "AdvertisementZone": """<fw type="ad">""",
    "DigitizationArtefactZone": """<fw type="digital">""",
    "DropCapitalZone": """<hi rend="dropcapital">""",
    "FigureZone": """<figure type="code">""",
    "FigureZone-FigDesc": """<figDesc>""",
    "FigureZone-Head": """<head>""",
    "GraphicZone": """<figure>""",
    "GraphicZone-Decoration": """<figure type="decoration">""",
    "GraphicZone-FigDesc": "<figDesc>""",
    "GraphicZone-Head": """<head>""",
    "GraphicZone-Maths": """<figure type="maths">""",
    "GraphicZone-Part": """<figure>""",
    "GraphicZone-TextualContent":  """<p>""",
    "MainZone-Date": """<dateline>""",
    "MainZone-Entry": ["""<div type="entry">""","<p>"],
    "MainZone-Form": ['<div type="form">', "<p>"],
    "MainZone-Head": """<head>""",
    "MainZone-Lg": '<lg>',
    "MainZone-List": ['<list>', '<item>'],
    "MainZone-Other": ['<div type="others">', "<p>"],
    "MainZone-P": """<p>""",
    "MainZone-P@CatalogueDesc": """<entry>""",
    "MainZone-Signature": ["""<div type="letter">""", """<closer>""", """<signed>"""],
    "MainZone-Sp": """<sp>""",
    "MarginTextZone-ManuscriptAddendum": """<fw type="margin">""",
    "MarginTextZone-Notes": """<note>""",
    "NumberingZone": """<fw type="numbering">""",
    "PageTitleZone": ["""<div type="titlepage">""",  """<p>"""],
    "PageTitleZone-Index": ["""<div type="toc">""", """<p>"""],
    "QuireMarkZone": """<fw type="quiremark">""",
    "RunningTitleZone": """<fw type="runningtitle">""",
    "StampZone": """<fw type="stamp">""",
    "StampZone-Sticker": """<fw type="sticker">""",
    "TableZone": """<figure type="table">""",
    "TableZone-Head":  """<head>""",
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

def fill_header(template_file, metadata):
    with open(template_file, 'r', encoding='utf-8') as file:
        template = file.read()
    placeholders = re.findall(r'\[(\w+)\]', template)
    replacements = { column: metadata.get(column, '') for column in placeholders}
    replacements['date_today'] = datetime.today().date()
    for placeholder, value in replacements.items():
        template = template.replace(f'[{placeholder}]', str(value))
    return template

def apply_xslt(xml_file, xslt_file):
    """
    Parses an XML file and applies an XSLT transformation.
    
    :param xml_file: Path to the input XML file.
    :param xslt_file: Path to the XSLT file.
    :return: Transformed XML tree or None in case of error.
    """
    try:
        xml_tree = ET.parse(xml_file)
        xslt_tree = ET.parse(xslt_file)
        transform = ET.XSLT(xslt_tree)
        return transform(xml_tree)
    except Exception as e:
        print(f"Error: {e}")
        return None


def process_line(zone, tag, n, n_zone):
    """
    Processes each zone in the XML and returns formatted lines.
    
    :param zone: The XML zone element.
    :param tag: Start tag for the zone.
    :param tag_end: End tag for the zone.
    :param n: Page number.
    :param n_line: Line number.
    :return: List of lines with corresponding tags.
    """
    liste_line = []
    n_line=0
    for line in zone.findall("line"):
        n_line += 1
        text = line.text
        if text:
            text = text.replace("&", "et")
        if tag == "MainZone-Lg":
            liste_line.append(f"<l><lb n='{n}_{n_zone}_{n_line}'/> {text}</l>")
        liste_line.append(f"<lb n='{n}_{n_zone}_{n_line}'/> " + (text or ""))
    
    return liste_line


def create_tag_end(tag):
    if isinstance(tag, list):
        tag = "".join(tag[::-1])
    cleaned_string = re.sub(r'<(\w+)(\s+[^>]*)?>', r'<\1>', tag)
    tag_end = cleaned_string.replace('<', '</')
    return tag_end



def update_block(liste_block, tag, liste_line, continued, cumul, is_list, zone_type):
    """
    Updates the block list by adding new content based on zone type, continued blocks, and cumulative blocks.
    
    :param liste_block: The list of blocks to be updated.
    :param tag: Start tag for the zone.
    :param tag_end: End tag for the zone.
    :param liste_line: List of processed lines.
    :param continued: Boolean indicating if the block is continued.
    :param cumul: Boolean indicating if the block is cumulative.
    :param n: Page number.
    :param zone_type: Type of the zone.
    :return: Updated list of blocks.
    """
    #if '<div type="titlepage">' in liste_block[-1] or '<div type="toc">' in liste_block[-1]:
    #liste_block.append("<div>")
    if continued:
        for i in range(len(liste_block)-1, -1, -1):
            last_block_zone = liste_block[i]
            if 'fw' in last_block_zone or 'pb' in last_block_zone:
                continue
            break
        pattern = r"<\/[^>]+>"
        matches = re.findall(pattern, last_block_zone)
        if matches:
            last_tag_end = ''.join(matches)
            modified_last_block_zone = re.sub(pattern, '', last_block_zone)
            liste_block[i] = modified_last_block_zone
            liste_block.append("".join(liste_line) + last_tag_end)
        else:
            print('pas de matches')

    elif cumul or is_list:
        last_block = liste_block[-1]
        last_tag = re.search('</[a-zA-Z]*>$', last_block)
        tag_end = create_tag_end(tag)
        if cumul:
            last_tag_needed = tei_mapping[cumulative[zone_type]]
        else:
            last_tag_needed = create_tag_end(tag[0])
        if last_tag and last_tag.group()==last_tag_needed:
            if is_list:
                tag_end = create_tag_end(tag[1])
                tag = tag[1]
            modified_block = last_block.replace(last_tag.group(), "") + tag + "".join(liste_line) + tag_end + last_tag.group()
            liste_block[-1] = modified_block
        else:
            liste_block.append("".join(tag) + "".join(liste_line) + tag_end)
    elif (zone_type=="MainZone-Head" and any("<head>" in el for el in liste_block)): 
        tag_end = create_tag_end(tag)
        liste_block.append("</div><div>"+tag + "".join(liste_line)+tag_end)
    else:
        tag_end = create_tag_end(tag)
        liste_block.append(tag + "".join(liste_line) + tag_end)
    
    return liste_block

def process_document(directory, doc, liste_block, xslt_file, n):
    """
    Processes each document in the directory, applies XSLT, and generates the corresponding TEI structure.
    
    :param doc: The document to be processed.
    :param xslt_file: Path to the XSLT file.
    :param directory: Directory containing the XML files.
    :param tei_mapping: Mapping for TEI elements.
    :param cumulative: Cumulative zones dictionary.
    """
    transformed_tree = apply_xslt(directory+'/'+doc, xslt_file)
    if transformed_tree:
        root = transformed_tree.getroot()
        liste_zone = root.findall('region')
        liste_block.append(f"<pb n='{n}' facs='{doc}'/>")
        n_zone = 0
        for zone in liste_zone:
            zone_type = zone.attrib.get('type', None)
            tag = tei_mapping.get(zone_type, '<ab>')
            continued = "Continued" in zone_type if zone_type else False
            cumul = cumulative.get(zone_type, False) if zone_type else False
            is_list = True if isinstance(tag, list) else False
            liste_line = process_line(zone, tag,n, n_zone)
            liste_block = update_block(liste_block, tag,liste_line, continued, cumul, is_list, zone_type)
            n_zone+=1
    return liste_block

    
@click.command()
@click.argument('csv_metadata', type=str)
@click.argument('pattern_header', type=str, required=False)
def ladas2tei(csv_metadata, pattern_header):
    with open(csv_metadata, newline='', encoding="utf-8") as csv_file:
        reader=csv.DictReader(csv_file)

        for row in reader:
            print(f'Traitement de {row["file_name"]}')
            root_xml = ET.Element("TEI", xmlns="http://www.tei-c.org/ns/1.0")
            if pattern_header:
                tei_header = fill_header(pattern_header, row)
            else:
                tei_header = fill_header('basic_header.txt', row)
            root_xml.append(ET.fromstring(tei_header))
            liste_block = ["<text><body><div>"]
            n = 0
            for xml_file in sorted(os.listdir(row["file_name"])):
                if 'xml' in xml_file and 'METS' not in xml_file:
                    liste_block = process_document(row['file_name'], xml_file, liste_block, xslt_file, n)
                    n+=1
            liste_block.append("</div></body></text>")
            block_str = "".join(liste_block)
            block_tei = ET.fromstring(block_str)
            root_xml.append(block_tei)

            with open(f'TEI/{row["file_name"].replace("picard_2021_sortie_rtk","")}.xml', "w") as f:
                f.write(ET.tostring(root_xml, encoding='unicode', pretty_print=True))
        
if __name__ == "__main__":
    ladas2tei()