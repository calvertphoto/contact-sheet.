import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from core import save_metadata, load_metadata, empty_metadata
from renaming import capture_date, rename_plan, apply_rename

class RenamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.paths=[self.root/'one.jpg',self.root/'two.jpg']
        for path in self.paths:
            exif=Image.Exif(); exif[0x8769]={0x9003:'2026:10:08 09:15:00'}
            Image.new('RGB',(30,20),'blue').save(path,exif=exif)
    def tearDown(self): self.temp.cleanup()
    def test_camera_date_sequence_and_sidecars_follow(self):
        self.assertEqual(capture_date(self.paths[0]).strftime('%Y%m%d'),'20261008')
        before=[p.read_bytes() for p in self.paths]
        data=empty_metadata(); data['caption']='Reno Aces';save_metadata(self.paths[0],data)
        plan=rename_plan(self.paths,'Aces',start=7,digits=3)
        result=apply_rename(plan)
        for i,path in enumerate(self.paths):
            self.assertEqual(result[path].name,f'Aces_20261008_{i+7:03}.jpg')
            self.assertEqual(result[path].read_bytes(),before[i]);self.assertFalse(path.exists())
        self.assertEqual(load_metadata(result[self.paths[0]])['caption'],'Reno Aces')
    def test_ddmmyy_format_and_sidecar(self):
        data=empty_metadata(); data['caption']='Reno Aces'; save_metadata(self.paths[0],data)
        plan=rename_plan([self.paths[0]],'Aces',1,4,True,'%d%m%y')
        self.assertEqual(plan.photos[0][1].name,'Aces_081026_0001.jpg')
        new=apply_rename(plan)[self.paths[0]]
        self.assertEqual(load_metadata(new)['caption'],'Reno Aces')

    def test_missing_date_does_not_use_file_modification_time(self):
        path=self.root/'no-date.jpg';Image.new('RGB',(10,10)).save(path)
        self.assertIsNone(capture_date(path))
        with self.assertRaises(ValueError): rename_plan([path])
        result=apply_rename(rename_plan([path],include_date=False))
        self.assertEqual(result[path].name,'Photo_0001.jpg')
    def test_case_insensitive_collision_aborts_before_changes(self):
        (self.root/'photo_20261008_0001.JPG').write_bytes(b'keep')
        with self.assertRaises(FileExistsError): rename_plan(self.paths)
        self.assertTrue(all(p.exists() for p in self.paths))
    def test_target_created_after_preview_is_not_overwritten(self):
        plan=rename_plan(self.paths);target=plan.photos[1][1];target.write_bytes(b'keep')
        with self.assertRaises(FileExistsError): apply_rename(plan)
        self.assertEqual(target.read_bytes(),b'keep');self.assertTrue(all(p.exists() for p in self.paths))
        self.assertFalse(plan.photos[0][1].exists())
    def test_shared_conventional_sidecar_stays_with_unselected_raw(self):
        raw=self.root/'one.nef';raw.write_bytes(b'raw')
        conventional=self.root/'one.xmp';conventional.write_text('<x/>')
        result=apply_rename(rename_plan([self.paths[0]]))
        self.assertTrue(conventional.exists());self.assertTrue(raw.exists())
        self.assertEqual(result[self.paths[0]].with_name(result[self.paths[0]].name+'.xmp').read_text(),'<x/>')
    def test_changed_source_requires_new_preview(self):
        plan=rename_plan(self.paths);self.paths[0].write_bytes(b'changed')
        with self.assertRaises(ValueError): apply_rename(plan)
        self.assertFalse(plan.photos[0][1].exists())
    def test_delete_failure_restores_originals(self):
        plan=rename_plan(self.paths)
        original=Path.unlink; calls=[0]
        def fail_once(path,*a,**kw):
            if path in self.paths:
                calls[0]+=1
                if calls[0]==2: raise OSError('simulated busy photo')
            return original(path,*a,**kw)
        with patch.object(Path,'unlink',fail_once):
            with self.assertRaises(OSError): apply_rename(plan)
        self.assertTrue(all(p.exists() for p in self.paths))
        self.assertFalse(any(target.exists() for _,target,_ in plan.photos))
    def test_fallback_copy_preserves_images(self):
        plan=rename_plan(self.paths)
        before=self.paths[0].read_bytes()
        with patch('renaming.os.link',side_effect=OSError('no hard links')): result=apply_rename(plan)
        self.assertEqual(result[self.paths[0]].read_bytes(),before)
