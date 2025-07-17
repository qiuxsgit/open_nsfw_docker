# -*- coding: utf-8 -*-
from flask import jsonify
import logging
import validators
import requests
from StringIO import StringIO
from PIL import Image

logger = logging.getLogger(__name__)

def make_error_response(message, param, status_code):
    logger.error(message)
    return jsonify({'error': message, 'param': param, 'status': 'failed'}), status_code

def validate_image(file):
    if not file or file.filename == '':
        return False, 'No file uploaded or empty filename'
    
    try:
        from PIL import Image
        file.seek(0)
        image = Image.open(file.stream)
        image.verify()
        file.seek(0)
        return True, None
    except Exception:
        return False, 'Invalid image file'

def download_image(url, timeout=5, max_size=10*1024*1024):
    """安全下载图片 (Python 2.7 版本)"""
    if not validators.url(url):
        raise ValueError("无效的URL格式")
    
    headers = {'User-Agent': 'NSFW Checker/1.0'}
    
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            stream=True
        )
        resp.raise_for_status()
        
        # 分块读取（Python 2.7 内存安全方式）
        content = ""
        chunk_size = 1024
        for chunk in resp.iter_content(chunk_size):
            content += chunk
            if len(content) > max_size:
                raise ValueError("图片大小超过10MB限制")
        
        # 验证图片有效性
        img = Image.open(StringIO(content))
        img.verify()
        return StringIO(content)
        
    except Exception as e:
        raise ValueError("图片下载失败: " + str(e))