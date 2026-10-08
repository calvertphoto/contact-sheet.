"""Photo access and non-destructive metadata for Contact Sheet."""
from __future__ import annotations
import io
import json
from iptc import FIELDS
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageOps, IptcImagePlugin

RAWS = {'.nef', '.nrw', '.cr2', '.cr3', '.arw', '.raf', '.dng', '.orf', '.rw2', '.pef', '.srw'}
FORMATS = RAWS | {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.bmp'}
NS = {'x': 'adobe:ns:meta/', 'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
      'dc': 'http://purl.org/dc/elements/1.1/', 'xmp': 'http://ns.adobe.com/xap/1.0/',
      'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
      'iptc': 'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
      'ext': 'http://iptc.org/std/Iptc4xmpExt/2008-02-29/',
      'plus': 'http://ns.useplus.org/ldf/xmp/1.0/',
      'rights': 'http://ns.adobe.com/xap/1.0/rights/'}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
def tag(prefix, name):
    return '{' + NS[prefix] + '}' + name

def photos(folder):
    return sorted((p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in FORMATS), key=lambda p: p.name.casefold())

def sidecar(path):
    """Use existing standard stem sidecar, otherwise a collision-safe full-name sidecar."""
    path = Path(path)
    full = path.with_name(path.name + '.xmp')
    conventional = path.with_suffix('.xmp')
    if full.exists():
        return full
    if conventional.exists():
        # A JPEG + RAW pair may share a conventional sidecar. Preserve it on read,
        # but writes go to our collision-safe per-image file.
        return conventional
    return full

def empty_metadata():
    return dict(rating=0, label='', caption='', creator='', copyright='', keywords=[])

def load_metadata(path):
    data = empty_metadata()
    file = sidecar(path)
    if file.exists():
        root = ET.parse(file).getroot()  # malformed sidecars must not be overwritten
        for desc in root.iter(tag('rdf', 'Description')):
            def value(prefix, name):
                key = tag(prefix, name)
                return desc.get(key) or desc.findtext(key, default='')
            rating = value('xmp', 'Rating')
            if rating:
                data['rating'] = max(-1, min(5, int(rating)))
            data['label'] = value('xmp', 'Label')
            for field, name in [('caption', 'description'), ('creator', 'creator'), ('copyright', 'rights')]:
                node = desc.find(tag('dc', name))
                if node is not None:
                    items = list(node.iter(tag('rdf', 'li')))
                    default = next((i for i in items if i.get('{http://www.w3.org/XML/1998/namespace}lang') == 'x-default'), None)
                    data[field] = (default if default is not None else items[0]).text or '' if items else node.text or ''
            node = desc.find(tag('dc', 'subject'))
            if node is not None:
                data['keywords'] = [i.text for i in node.iter(tag('rdf', 'li')) if i.text]
        for key, (_, _, prefix, name, kind) in FIELDS.items():
            if key in ('creator', 'copyright', 'keywords'): continue
            for desc in root.iter(tag('rdf', 'Description')):
                parent = desc.find(tag('iptc', 'CreatorContactInfo')) if kind == 'contact' else desc
                if parent is None: continue
                node = parent.find(tag(prefix, name))
                value = parent.get(tag(prefix, name))
                if node is None and value is None: continue
                if kind == 'json':
                    rows = []
                    for li in node.findall('./' + tag('rdf','Bag') + '/' + tag('rdf','li')):
                        row = {k.split('}')[-1]: v for k, v in li.attrib.items() if k != tag('rdf','parseType')}
                        for child in li:
                            items = list(child.iter(tag('rdf','li')))
                            row[child.tag.split('}')[-1]] = [i.text or '' for i in items] if items else child.text or ''
                        rows.append(row)
                    data[key] = json.dumps(rows, ensure_ascii=False)
                elif kind in ('Bag','Seq','Alt') and node is not None:
                    items = list(node.iter(tag('rdf','li')))
                    if kind == 'Alt':
                        default = next((i for i in items if i.get('{http://www.w3.org/XML/1998/namespace}lang') == 'x-default'), None)
                        data[key] = (default if default is not None else items[0]).text or '' if items else node.text or ''
                    else: data[key] = '; '.join(i.text or '' for i in items)
                else: data[key] = value if value is not None else node.text or ''
        return data
    # Read common legacy IPTC fields from JPEG/TIFF originals, without writing them.
    if Path(path).suffix.lower() not in RAWS:
        try:
            with Image.open(path) as img:
                iptc = IptcImagePlugin.getiptcinfo(img) or {}
                utf8 = iptc.get((1, 90)) == b'\x1b%G'
                def decode(v):
                    return v.decode('utf-8' if utf8 else 'latin-1', errors='replace') if isinstance(v, bytes) else str(v)
                for field, key in [('caption', 120), ('creator', 80), ('copyright', 116)]:
                    if (2, key) in iptc:
                        data[field] = decode(iptc[(2, key)])
                words = iptc.get((2, 25), [])
                data['keywords'] = [decode(x) for x in (words if isinstance(words, list) else [words])]
        except (OSError, ValueError):
            pass
    return data

def save_metadata(path, data):
    path = Path(path)
    source = sidecar(path)
    target = path.with_name(path.name + '.xmp')
    if source.exists():
        tree = ET.parse(source)
        root = tree.getroot()
    else:
        root = ET.Element(tag('x', 'xmpmeta'))
        ET.SubElement(root, tag('rdf', 'RDF'))
        tree = ET.ElementTree(root)
    rdf = root.find('.//' + tag('rdf', 'RDF'))
    if rdf is None:
        raise ValueError('Sidecar does not contain RDF metadata; left unchanged.')
    descriptions = list(rdf.findall(tag('rdf', 'Description')))
    desc = descriptions[0] if descriptions else ET.SubElement(rdf, tag('rdf', 'Description'), {tag('rdf', 'about'): ''})
    # Remove only fields we own, from every description, preserving all other XML.
    owned = [tag('xmp', n) for n in ['Rating', 'Label']] + [tag('dc', n) for n in ['description', 'creator', 'rights', 'subject']]
    for d in descriptions:
        for key in owned:
            d.attrib.pop(key, None)
            for child in list(d):
                if child.tag == key:
                    d.remove(child)
    rating = int(data.get('rating', 0))
    if rating not in range(-1, 6):
        raise ValueError('Rating must be -1 through 5.')
    desc.set(tag('xmp', 'Rating'), str(rating))
    desc.set(tag('xmp', 'Label'), data.get('label', ''))
    for field, name, container in [('caption', 'description', 'Alt'), ('creator', 'creator', 'Seq'), ('copyright', 'rights', 'Alt')]:
        node = ET.SubElement(ET.SubElement(desc, tag('dc', name)), tag('rdf', container))
        li = ET.SubElement(node, tag('rdf', 'li'))
        if container == 'Alt':
            li.set('{http://www.w3.org/XML/1998/namespace}lang', 'x-default')
        li.text = data.get(field, '')
    bag = ET.SubElement(ET.SubElement(desc, tag('dc', 'subject')), tag('rdf', 'Bag'))
    for word in data.get('keywords', []):
        ET.SubElement(bag, tag('rdf', 'li')).text = word
    for key, (_, _, prefix, name, kind) in FIELDS.items():
        if key not in data or key in ('creator','copyright','keywords'): continue
        value = data[key]
        prop = tag(prefix, name)
        parent = desc
        if kind == 'contact':
            parent = desc.find(tag('iptc','CreatorContactInfo'))
            if parent is None: parent = ET.SubElement(desc, tag('iptc','CreatorContactInfo'), {tag('rdf','parseType'): 'Resource'})
            for d in descriptions:
                contact = d.find(tag('iptc','CreatorContactInfo'))
                if contact is not None:
                    contact.attrib.pop(prop, None)
                    for child in list(contact):
                        if child.tag == prop: contact.remove(child)
        else:
            for d in descriptions:
                d.attrib.pop(prop, None)
                for child in list(d):
                    if child.tag == prop: d.remove(child)
        if not value: continue
        node = ET.SubElement(parent, prop)
        if kind == 'json':
            rows = json.loads(value)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f'{key} must be a JSON list of objects.')
            bag = ET.SubElement(node, tag('rdf','Bag'))
            for row in rows:
                li = ET.SubElement(bag, tag('rdf','li'), {tag('rdf','parseType'): 'Resource'})
                for field, item in row.items():
                    child = ET.SubElement(li, tag(prefix, field))
                    if isinstance(item, list):
                        seq = ET.SubElement(child, tag('rdf','Seq'))
                        for entry in item: ET.SubElement(seq,tag('rdf','li')).text = str(entry)
                    else: child.text = str(item)
        elif kind in ('Bag','Seq','Alt'):
            container = ET.SubElement(node, tag('rdf',kind))
            for item in ([value] if kind == 'Alt' else [x.strip() for x in value.split(';') if x.strip()]):
                li = ET.SubElement(container, tag('rdf','li'))
                if kind == 'Alt': li.set('{http://www.w3.org/XML/1998/namespace}lang','x-default')
                li.text = item
        else: node.text = value
    fd, temp = tempfile.mkstemp(prefix='.contact-sheet-', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            tree.write(output, encoding='utf-8', xml_declaration=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target

def preview(path, size=(1400, 1000), full=False):
    path = Path(path)
    if path.suffix.lower() in RAWS:
        try:
            import rawpy
        except ImportError as exc:
            raise RuntimeError('RAW preview requires rawpy. Run the RAW install command in README.') from exc
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    with Image.open(io.BytesIO(thumb.data)) as image:
                        result = ImageOps.exif_transpose(image).convert('RGB')
                else:
                    result = Image.fromarray(thumb.data)
            except rawpy.LibRawNoThumbnailError:
                result = Image.fromarray(raw.postprocess(half_size=True, use_camera_wb=True))
    else:
        with Image.open(path) as image:
            if not full and image.format == 'JPEG':
                image.draft('RGB', size)
            result = ImageOps.exif_transpose(image).convert('RGB')
    if not full:
        result.thumbnail(size, Image.Resampling.LANCZOS)
    return result

def export_photos(paths, destination):
    """Copy photos and their sidecars; refuse collisions and never delete originals."""
    destination = Path(destination)
    if not destination.is_dir():
        raise ValueError('Choose an existing destination folder.')
    jobs = []
    for path in paths:
        path = Path(path)
        jobs.append((path, destination / path.name))
        meta = sidecar(path)
        if meta.exists():
            jobs.append((meta, destination / (path.name + '.xmp')))
    targets = [dst for _, dst in jobs]
    if len(set(targets)) != len(targets) or any(p.exists() for p in targets):
        raise FileExistsError('Destination contains matching filenames. Choose an empty folder.')
    for source, target in jobs:
        # exclusive creation avoids overwriting a file added after preflight
        try:
            with source.open('rb') as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
        except FileExistsError:
            raise
        except Exception:
            target.unlink(missing_ok=True)
            raise
        shutil.copystat(source, target)
    return len(paths)
