# -*- coding: utf-8 -*-
import unittest
import os
from io import BytesIO
from PIL import Image
import numpy as np
from ..wsgi import app

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
        # 创建测试图片
        self.valid_img = BytesIO()
        Image.new('RGB', (100, 100)).save(self.valid_img, 'JPEG')
        self.valid_img.seek(0)
        
        self.invalid_img = BytesIO(b'invalid')
        self.invalid_img.seek(0)

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'healthy')

    def test_score_valid_image(self):
        data = {'file': (self.valid_img, 'test.jpg')}
        response = self.app.post('/score', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn('score', response.json)
        self.assertIsInstance(response.json['score'], float)

    def test_score_no_file(self):
        response = self.app.post('/score')
        self.assertEqual(response.status_code, 400)

    def test_score_invalid_image(self):
        data = {'file': (self.invalid_img, 'test.jpg')}
        response = self.app.post('/score', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)