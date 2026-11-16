"""Read populated IPTC/XMP template fields without importing photo-specific ratings."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from core import tag
from iptc import FIELDS

XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'

def read_template(path):
    """Return only populated, supported metadata keys from an XMP template.

    Accepts RDF XMP (.xmp/.xml), not binary legacy IPTC IIM (.iptc).
    Missing or blank properties are intentionally omitted.
    """
    path = Path(path)
    if path.suffix.lower() not in ('.xmp', '.xml'):
        raise ValueError('Choose an XMP metadata template (.xmp or .xml). Binary .iptc files are not supported.')
    root = ET.parse(path).getroot()
    descriptions = list(root.iter(tag('rdf', 'Description')))
    if not descriptions:
        raise ValueError('This file has no RDF/XMP description. No photographs were changed.')

    result = {}
    mappings = [('caption', 'dc', 'description', 'Alt'),
                ('creator', 'dc', 'creator', 'Seq'),
                ('copyright', 'dc', 'rights', 'Alt'),
                ('keywords', 'dc', 'subject', 'Bag')]
    mappings += [(key, prefix, name, kind) for key, (_, _, prefix, name, kind) in FIELDS.items()
                 if key not in ('creator', 'copyright', 'keywords')]
    for key, prefix, name, kind in mappings:
        for desc in descriptions:
            parent = desc.find(tag('iptc', 'CreatorContactInfo')) if kind == 'contact' else desc
            if parent is None:
                continue
            prop = tag(prefix, name)
            node = parent.find(prop)
            attr = parent.get(prop)
            if node is None and attr is None:
                continue
            if kind == 'json':
                rows = []
                if node is not None:
                    for item in node.iter(tag('rdf', 'li')):
                        # Only outer structured rows, not nested list members.
                        if item.get(tag('rdf', 'parseType')) == 'Resource' or item.attrib or list(item):
                            row = {k.split('}')[-1]: v for k, v in item.attrib.items()
                                   if k != tag('rdf', 'parseType') and k != XML_LANG}
                            for child in item:
                                elements = list(child.iter(tag('rdf', 'li')))
                                row[child.tag.split('}')[-1]] = [e.text or '' for e in elements] if elements else child.text or ''
                            if row:
                                rows.append(row)
                value = json.dumps(rows, ensure_ascii=False) if rows else ''
            elif kind in ('Alt', 'Seq', 'Bag'):
                items = list(node.iter(tag('rdf', 'li'))) if node is not None else []
                if kind == 'Bag' and key == 'keywords':
                    value = [i.text.strip() for i in items if i.text and i.text.strip()]
                elif kind == 'Alt':
                    default = next((i for i in items if i.get(XML_LANG) == 'x-default'), None)
                    item = default if default is not None else (items[0] if items else None)
                    value = ((item.text if item is not None else (node.text if node is not None else attr)) or '').strip()
                elif kind == 'Seq' and key == 'creator':
                    value = (items[0].text or '').strip() if items else ((node.text if node is not None else attr) or '').strip()
                else:
                    value = '; '.join(i.text.strip() for i in items if i.text and i.text.strip())
            else:
                value = (attr if attr is not None else (node.text if node is not None else '')) or ''
                value = value.strip()
            if value:
                result[key] = value
                break
    if not result:
        raise ValueError('The template contains no populated IPTC fields supported by Contact Sheet.')
    return result
