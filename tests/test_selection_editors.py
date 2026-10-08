import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from selection import PhotoSelection
from editors import open_in_editor

class SelectionTests(unittest.TestCase):
    def test_range_across_pages_toggle_filter_and_order(self):
        paths=list(range(30)); selection=PhotoSelection()
        selection.click(2,paths); selection.click(17,paths,extend=True)
        self.assertEqual(selection.ordered(paths),list(range(2,18)))
        selection.click(8,paths,toggle=True)
        self.assertNotIn(8,selection.selected)
        selection.retain_visible([2,3,17])
        self.assertEqual(selection.ordered(paths),[2,3,17])
        selection.select_all(paths); self.assertEqual(len(selection.selected),30)
        selection.clear(); self.assertEqual(selection.selected,set())

class EditorTests(unittest.TestCase):
    def test_mac_paths_with_spaces_and_punctuation_remain_separate_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); editor=root/'Adobe Photoshop.app'; editor.mkdir()
            paths=[root/'first photo.jpg',root/'second;photo.jpg']
            for path in paths: path.touch()
            with patch('editors.sys.platform','darwin'),patch('editors.subprocess.run') as run:
                run.return_value.returncode=0
                self.assertEqual(open_in_editor(paths,editor),2)
                self.assertEqual(run.call_args.args[0],['/usr/bin/open','-a',str(editor),*[str(p) for p in paths]])
    def test_missing_image_prevents_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            editor=Path(folder)/'editor'; editor.touch()
            with patch('editors.subprocess.Popen') as launch:
                with self.assertRaises(FileNotFoundError): open_in_editor([Path(folder)/'missing.jpg'],editor)
                launch.assert_not_called()
