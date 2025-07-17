# -*- coding: utf-8 -*-
import unittest
import StringIO
from app import app

class TestURLProcessing(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        
    def test_valid_url(self):
        mock_image = StringIO.StringIO()
        Image.new('RGB', (100, 100)).save(mock_image, 'JPEG')
        mock_image.seek(0)
        
        with requests_mock.Mocker() as m:
            m.get('http://valid.url', content=mock_image.getvalue())
            response = self.app.post('/score_url', 
                                   data='{"url": "http://valid.url"}',
                                   content_type='application/json')
            self.assertEqual(response.status_code, 200)