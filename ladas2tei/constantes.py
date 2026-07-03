TEI_NS = "http://www.tei-c.org/ns/1.0"
ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: TEI_NS}


def qname(local_name: str) -> str:
    """Construit un nom XML qualifie dans le namespace TEI.

    :param local_name: nom local de l'element TEI.
    :type local_name: str

    :return: Nom XML complet utilisable par lxml.
    :rtype: str
    """
    return f"{{{TEI_NS}}}{local_name}"
