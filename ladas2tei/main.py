import os
import click
from lxml import etree as ET
from datetime import datetime
import csv
import re
import pkg_resources

tei_mapping_level_1 = {
    "MarginTextZone":{"tag":"note", "cumul":True},
    "TitlePageZone": {"tag":"div", "attrib":{"type": "titlePage"}, "cumul":True},
    "GraphicZone": {"tag":"figure", "cumul":True},
    "FigureZone":{"tag":"figure", "attrib":{"type":"code"}, "cumul":True},
    "TableZone":{"tag":"figure", "attrib":{"type": "table"}, "cumul":True},
    "FormZone":{"tag":"figure", "attrib":{"type":"form"}, "cumul":True},
    "MusicZone": {"tag":"notatedMusic"},
    "DigitisationArtefactZone":{"tag":"ab", "attrib":{"type":"digitisation-artefact"}},
    "NumberingZone":{"tag":"fw", "attrib":{"type":"numbering"}},
    "RunningTitleZone":{"tag":"fw", "attrib":{"type":"runningTitle"}},
    "StampZone":{"tag":"stamp"},
    "QuireMarks":{"tag":"fw", "attrib":{"type": "quiremarks"}}}

tei_mapping_level_2 = {
    "Head":{"tag":"head"},
    "HeadStructured":{"tag":"head", "attrib":{"type":"structured"}},
    "P":{"tag":"p"},
    "PLabelled":{"tag":"p", "attrib":{"rend":"labelled"}},
    "PStructured":{"tag":"p", "attrib":{"rend":"structured"}},
    "PQuoted":{"tag":"quote"},
    "PStyled":{"tag":"p", "attrib":{"rend":"styled"}},
    "Item":{"tag":"item"},
    "Lg":{"tag":"lg"},
    "Dateline":{"tag":"dateline"},
    "Address":{"tag":"address"},
    "Signed":{"tag":"signed"},
    "Ab":{"tag":"ab"},
    "Part":{"tag":"graphic"},
    "Continued":{"tag":"p", "attrib":{"rend":"continued"}}
}






def apply_xslt(xml_file):
    """
    Parses an XML file and applies an XSLT transformation.
    
    :param xml_file: Path to the input XML file.
    :type xml_file: str
    :return: Transformed XML tree or None in case of error.
    :rtype: ElementTree
    """
    xslt_file = "alto2XMLsimple.xsl"
    try:
        xml_tree = ET.parse(xml_file)
        xslt_tree = ET.parse(xslt_file)
        transform = ET.XSLT(xslt_tree)
        return transform(xml_tree)
    except Exception as e:
        print(f"Error: {e}")
        return None


def process_line(zone, xml_tag):
    n_line=0
    for line in zone.findall("line"):
        n_line +=1
        text = line.text
        lb = ET.Element('lb', n=str(n_line))
        xml_tag.append(lb)
        lb.tail = text

def get_content_xml(level, tei_mapping, zone):
    print(level)
    level_dict = tei_mapping.get(level)
    attributes = level_dict.get("attrib")
    cumul = level_dict.get("cumul")
    tag = level_dict.get("tag")
    if attributes:
        child = ET.Element(tag, attrib=attributes)
    else:
        child = ET.Element(tag)
    return child, tag, cumul


@click.command()
def main():
    root_xml = root_xml = ET.Element("TEI", xmlns="http://www.tei-c.org/ns/1.0")
    text_xml = ET.SubElement(root_xml, "text")
    body_xml = ET.SubElement(text_xml, "body")
    div_xml = ET.SubElement(body_xml,"div")
    n_img = 0
    n_zone=0
    for xml_file in sorted(os.listdir('test')):
        print(xml_file)
        if 'xml' in xml_file and 'METS' not in xml_file:
            n_img+=1
            transformed_tree = apply_xslt('test/'+xml_file)
            with open(f'test_transformed.xml', "w") as f:
                f.write(ET.tostring(transformed_tree, encoding='unicode', pretty_print=True))
            if transformed_tree:
                root = transformed_tree.getroot()
                liste_zone = root.findall('region')
                for zone in liste_zone:
                    zone_type = zone.attrib.get('type')
                    if '-' in zone_type:
                        level1 = re.findall(r'^([A-Za-z]*)-', zone_type)[0]
                        level2 = re.findall(r'-([A-Za-z]*)', zone_type)[0]
                    else:
                        level1 = zone_type
                        level2=False
                    
                    if level2:
                        if "MainZone":
                            child_level2, tag2, cumul2 = get_content_xml(level2, tei_mapping_level_2, zone)
                            process_line(zone, child_level2)
                            div_xml.append(child_level2)
                        else:
                            child_level1, tag1, cumul = get_content_xml(level1, tei_mapping_level_1, zone)
                            child_level2, tag2, cumul2 = get_content_xml(level2, tei_mapping_level_2, zone)
                            process_line(zone, child_level2)
                            if cumul:
                                last_node = div_xml[-1]
                                if last_node.tag == level1:
                                    last_node.append(child_level2)
                            else:
                                child_level1.append(child_level2)
                                div_xml.append(child_level1)
                    else:
                        child_level1, tag1, cumul = get_content_xml(level1, tei_mapping_level_1, zone)
                        process_line(zone, child_level1)
                        try:
                            last_node=div_xml[-1]
                            last_node.append(child_level1)
                        except IndexError as e:
                            div_xml.append(child_level1)


    with open(f'test.xml', "w") as f:
        f.write(ET.tostring(root_xml, encoding='unicode', pretty_print=True))


if __name__ == "__main__":
    main()