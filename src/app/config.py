# -*- coding: utf-8 -*-
import os

class Config:
    MODEL_DIR = os.getenv('MODEL_DIR', '/workspace/nsfw_model')
    MODEL_DEF = os.path.join(MODEL_DIR, 'deploy.prototxt')
    PRETRAINED_MODEL = os.path.join(MODEL_DIR, 'resnet_50_1by2_nsfw.caffemodel')
    
    # 直接读取密码文件内容
    try:
        with open('/py_config/password.txt', 'r') as f:
            PASSWORD = f.read().strip()
        print("读取密码成功", PASSWORD)
    except IOError:  # 在Python 2.7中使用IOError
        PASSWORD = None
        print("警告: 未找到密码文件")

    @staticmethod
    def init_app(app):
        pass

config = Config()