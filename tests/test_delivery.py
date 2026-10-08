import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from delivery import Destination, upload_files, validate

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / 'photo.jpg'
        self.file.write_bytes(b'example photograph')
    def tearDown(self):
        self.temp.cleanup()
    def test_validation(self):
        with self.assertRaises(ValueError):
            validate(Destination('NOT_A_PROTOCOL','host','user','pass'))
        with self.assertRaises(ValueError):
            validate(Destination('FTPS','','user','pass'))
        with self.assertRaises(ValueError):
            validate(Destination('FTPS','host','user','pass',port=70000))
    @patch('delivery.FTP_TLS')
    def test_ftps_encrypts_data_channel(self, factory):
        client = factory.return_value.__enter__.return_value
        progress = []
        total = upload_files([self.file], Destination('FTPS','example.org','user','pass'),
                             progress=lambda *args: progress.append(args))
        self.assertEqual(total, 1)
        client.prot_p.assert_called_once()
        client.storbinary.assert_called_once()
        self.assertEqual(progress[0][:3], (1,1,'photo.jpg'))
    def test_photoshelter_is_not_an_option(self):
        with self.assertRaises(ValueError):
            validate(Destination('PhotoShelter','server','user','pass'))
    @patch('delivery._ftp_one',side_effect=[OSError('offline'),None])
    @patch('delivery.time.sleep')
    def test_retry(self, sleep, transfer):
        self.assertEqual(upload_files([self.file],Destination('FTP','server','user','pass')),1)
        self.assertEqual(transfer.call_count,2)
    def test_duplicate_names_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        second = other / 'photo.jpg'
        second.write_bytes(b'two')
        with self.assertRaises(ValueError):
            upload_files([self.file,second],Destination('FTP','server','user','pass'))
if __name__ == '__main__': unittest.main()
