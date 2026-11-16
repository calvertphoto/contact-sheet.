"""Tests for importing prepopulated IPTC/XMP templates."""
import tempfile
import unittest
from pathlib import Path

from core import empty_metadata, load_metadata, save_metadata
from template_import import read_template

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"
 xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
 xmlns:xmp="http://ns.adobe.com/xap/1.0/">
 <rdf:RDF><rdf:Description xmp:Rating="5" photoshop:City="Reno" photoshop:Credit="Example Agency">
 <dc:description><rdf:Alt><rdf:li xml:lang="x-default">Photo from the game</rdf:li></rdf:Alt></dc:description>
 <dc:creator><rdf:Seq><rdf:li>Staff photographer</rdf:li></rdf:Seq></dc:creator>
 <dc:subject><rdf:Bag><rdf:li>sports</rdf:li><rdf:li>baseball</rdf:li></rdf:Bag></dc:subject>
 </rdf:Description></rdf:RDF>
</x:xmpmeta>
"""

class TemplateImportTests(unittest.TestCase):
    def test_read_only_populated_fields_and_ignore_rating(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'template.xmp'
            path.write_text(SAMPLE, encoding='utf-8')
            fields = read_template(path)
            self.assertEqual(fields['caption'], 'Photo from the game')
            self.assertEqual(fields['creator'], 'Staff photographer')
            self.assertEqual(fields['keywords'], ['sports', 'baseball'])
            self.assertEqual(fields['city'], 'Reno')
            self.assertEqual(fields['credit'], 'Example Agency')
            self.assertNotIn('rating', fields)
            self.assertNotIn('label', fields)
            self.assertNotIn('copyright', fields)

    def test_applied_fields_preserve_existing_rating_and_blank_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / 'template.xmp'
            template.write_text(SAMPLE, encoding='utf-8')
            photo = Path(tmp) / 'frame.jpg'
            photo.write_bytes(b'not decoded, because metadata uses a sidecar')
            before = dict(empty_metadata(), rating=3, label='Green', copyright='Existing rights')
            save_metadata(photo, before)
            updated = dict(load_metadata(photo))
            updated.update(read_template(template))
            save_metadata(photo, updated)
            after = load_metadata(photo)
            self.assertEqual(after['rating'], 3)
            self.assertEqual(after['label'], 'Green')
            self.assertEqual(after['copyright'], 'Existing rights')
            self.assertEqual(after['city'], 'Reno')
            self.assertEqual(after['keywords'], ['sports', 'baseball'])
            self.assertEqual(photo.read_bytes(), b'not decoded, because metadata uses a sidecar')

    def test_reject_non_xmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'template.iptc'
            path.write_bytes(b'legacy iptc')
            with self.assertRaisesRegex(ValueError, 'Binary'):
                read_template(path)

if __name__ == '__main__':
    unittest.main()
