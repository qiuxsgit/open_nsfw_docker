# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from .models import NSFWClassifier
from .utils import make_error_response, validate_image
from .config import config
import logging

logger = logging.getLogger(__name__)
classifier = NSFWClassifier()

def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

    app = Flask(__name__)
    
    @app.route('/health', methods=['GET'])
    def health_check():
        if classifier.net is None:
            return make_error_response("model not loaded", '', 200)
        return jsonify({"status": "healthy"}), 200
    
    @app.route('/score', methods=['POST'])
    def score_image():
        if not check_password(request):
            return make_error_response("密码错误", '', 200)
        
        if 'file' not in request.files:
            return make_error_response('No file uploaded', '', 200)
        
        file = request.files['file']
        is_valid, message = validate_image(file)
        if not is_valid:
            return make_error_response(message, 200)
        
        try:
            score = classifier.predict(file.read())
            return jsonify({
                'score': score,
                'status': 'success',
                'filename': file.filename
            })
        except Exception as e:
            return make_error_response(str(e), file.filename, 200)
    
    @app.route('/score_url', methods=['POST'])
    def score_from_url():
        if not check_password(request):
            return make_error_response("密码错误", '', 200)

        # 打印json
        logger.info("Received request: %s", request.json)
        
        if not request.json or 'url' not in request.json:
            return jsonify({'error': '缺少URL参数'}), 200

        url = request.json['url']
        
        try:
            score = classifier.predict_from_url(request.json['url'])
            return jsonify({
                'url': request.json['url'],
                'score': score,
                'status': 'success'
            })
        except Exception as e:
            return make_error_response(str(e), url, 200)

    def check_password(request):
        if request.headers.get('api-key') == config.PASSWORD:
            logger.info("密码验证通过")
            return True
        else:
            logger.warning("密码验证失败(请求密码=%s)", 
                        request.headers.get('api-key'))
            return False

    return app