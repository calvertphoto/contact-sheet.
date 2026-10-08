"""Real Tk smoke checks, run on desktop CI hosts; skip headless Linux."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from app import ContactSheet
from core import empty_metadata, load_metadata

@unittest.skipIf(sys.platform.startswith('linux') and not os.environ.get('DISPLAY'), 'No graphical display available')
class DesktopSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = [self.root/'one.jpg', self.root/'two.jpg']
        for p in self.paths: Image.new('RGB', (80,40), 'blue').save(p)
        self.app = ContactSheet()
        self.app.withdraw()
        self.app.paths = self.paths
        self.app.metadata = {p: empty_metadata() for p in self.paths}
        self.app.filter_photos()
        self.app.update_idletasks()
    def tearDown(self):
        self.app.pool.shutdown(wait=True, cancel_futures=True)
        self.app.preview_pool.shutdown(wait=True, cancel_futures=True)
        self.app.destroy()
        self.temp.cleanup()
    def test_caption_navigation_and_rating(self):
        app = self.app
        app.select(self.paths[0])
        app.caption.delete('1.0', 'end')
        app.caption.insert('1.0', 'Reno Aces play at home.')
        app.fields['creator'].set('David Calvert')
        app.dirty = True
        app.move(1)
        self.assertEqual(load_metadata(self.paths[0])['caption'], 'Reno Aces play at home.')
        self.assertEqual(app.current, self.paths[1])
        app.rate(5)
        app.rate(label='Green')
        self.assertEqual(load_metadata(self.paths[1])['rating'], 5)
        self.assertEqual(app.picks(), [self.paths[1]])
    def test_filters_and_clear(self):
        app = self.app
        app.select(self.paths[0])
        app.rate(-1, '')
        app.filter.set('Rejected')
        app.filter_photos()
        self.assertEqual(app.visible, [self.paths[0]])
        app.rate(0, '')
        self.assertEqual(app.visible, [])
        app.filter.set('All photos')
        app.search.set('two')
        self.assertEqual(app.visible, [self.paths[1]])

if __name__ == '__main__': unittest.main()
