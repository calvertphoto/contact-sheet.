import tempfile
import json
import unittest
from pathlib import Path
from PIL import Image
from core import load_metadata, save_metadata, empty_metadata
from iptc import FIELDS

class ExtendedMetadataTests(unittest.TestCase):
    def test_all_sections_round_trip_and_partial_update_preserves_extended_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            photo=Path(folder)/'image.jpg'; Image.new('RGB',(20,20)).save(photo)
            data=empty_metadata()
            for key,(_,_,prefix,name,kind) in FIELDS.items():
                if key in ('creator','copyright','keywords'): continue
                data[key]=json.dumps([{'City':'Reno','Names':['One','Two']}]) if kind=='json' else 'Reno; Nevada' if kind in ('Bag','Seq') else 'Café — Nevada'
            save_metadata(photo,data)
            self.assertEqual(load_metadata(photo),data)
            partial=empty_metadata(); partial['rating']=5
            save_metadata(photo,partial)
            result=load_metadata(photo)
            self.assertEqual(result['rating'],5)
            for key in data.keys()-partial.keys(): self.assertEqual(result[key],data[key])
    def test_invalid_structure_leaves_existing_sidecar_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            photo=Path(folder)/'image.jpg'; Image.new('RGB',(20,20)).save(photo)
            file=save_metadata(photo,empty_metadata()); original=file.read_bytes()
            data=empty_metadata(); data['licensors']='not JSON'
            with self.assertRaises(ValueError): save_metadata(photo,data)
            self.assertEqual(file.read_bytes(),original)
