import hashlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image
from core import photos, preview, load_metadata, save_metadata, export_photos, empty_metadata, tag, sidecar

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.photo = self.root/'test.jpg'
        Image.new('RGB', (400, 200), '#123456').save(self.photo)
    def tearDown(self):
        self.temp.cleanup()
    def metadata(self):
        return dict(rating=4, label='Green', caption='Reno — café & baseball <today>', creator='David Calvert', copyright='© 2026 David Calvert', keywords=['Reno', 'Aces', '日本語'])
    def test_round_trip_preserves_original(self):
        before = hashlib.sha256(self.photo.read_bytes()).digest()
        save_metadata(self.photo, self.metadata())
        self.assertEqual(load_metadata(self.photo), self.metadata())
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).digest(), before)
    def test_unknown_metadata_preserved_and_duplicate_fields_removed(self):
        xmp = self.photo.with_suffix('.xmp')
        xmp.write_text('''<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:custom="urn:custom"><rdf:RDF><rdf:Description custom:secret="kept" xmp:Rating="1"/><rdf:Description xmp:Rating="2"><custom:thing>hello</custom:thing></rdf:Description></rdf:RDF></x:xmpmeta>''')
        original = xmp.read_bytes()
        file = save_metadata(self.photo, self.metadata())
        root = ET.parse(file).getroot()
        self.assertEqual(root.find('.//'+tag('rdf','Description')).get('{urn:custom}secret'), 'kept')
        self.assertEqual(root.find('.//{urn:custom}thing').text, 'hello')
        self.assertEqual(load_metadata(self.photo)['rating'], 4)
        self.assertEqual(xmp.read_bytes(), original)
    def test_pair_has_separate_sidecars(self):
        raw = self.root/'test.nef'
        raw.write_bytes(b'dummy')
        save_metadata(raw, self.metadata())
        other = empty_metadata()
        other['rating'] = 1
        save_metadata(self.photo, other)
        self.assertEqual(load_metadata(raw)['rating'], 4)
        self.assertEqual(load_metadata(self.photo)['rating'], 1)
    def test_malformed_metadata_never_overwritten(self):
        file = self.photo.with_name(self.photo.name+'.xmp')
        file.write_text('<bad')
        before = file.read_bytes()
        with self.assertRaises(ET.ParseError): save_metadata(self.photo, self.metadata())
        self.assertEqual(file.read_bytes(), before)
    def test_invalid_rating_keeps_existing_file(self):
        file = save_metadata(self.photo, self.metadata())
        before = file.read_bytes()
        data = self.metadata()
        data['rating'] = 6
        with self.assertRaises(ValueError): save_metadata(self.photo, data)
        self.assertEqual(file.read_bytes(), before)
    def test_export_copies_photo_sidecar_without_reencoding(self):
        save_metadata(self.photo, self.metadata())
        dest = self.root/'export'
        dest.mkdir()
        self.assertEqual(export_photos([self.photo], dest), 1)
        self.assertEqual((dest/self.photo.name).read_bytes(), self.photo.read_bytes())
        self.assertEqual(load_metadata(dest/self.photo.name), self.metadata())
    def test_export_preflight_prevents_partial_copy_on_collision(self):
        dest = self.root/'export'
        dest.mkdir()
        save_metadata(self.photo, self.metadata())
        (dest/'test.jpg.xmp').write_text('keep me')
        with self.assertRaises(FileExistsError): export_photos([self.photo], dest)
        self.assertFalse((dest/'test.jpg').exists())
        self.assertEqual((dest/'test.jpg.xmp').read_text(), 'keep me')
    def test_exif_orientation(self):
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB',(400,200)).save(self.photo,exif=exif)
        self.assertEqual(preview(self.photo, (400,400)).size, (200,400))
    def test_preview_bounds_and_folder_scan(self):
        self.assertEqual(preview(self.photo, (100,100)).size, (100,50))
        (self.root/'notes.txt').write_text('ignored')
        (self.root/'nested').mkdir()
        Image.new('RGB',(10,10)).save(self.root/'nested'/'hidden.jpg')
        self.assertEqual(photos(self.root),[self.photo])
    def test_reject_and_clear(self):
        data = empty_metadata()
        data['rating'] = -1
        save_metadata(self.photo, data)
        self.assertEqual(load_metadata(self.photo)['rating'], -1)
        save_metadata(self.photo, empty_metadata())
        self.assertEqual(load_metadata(self.photo), empty_metadata())

if __name__ == '__main__': unittest.main()
