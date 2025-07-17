# -*- coding: utf-8 -*-
import numpy as np
import caffe
from PIL import Image
from io import BytesIO
import logging
from .config import config
from utils import download_image

logger = logging.getLogger(__name__)

class NSFWClassifier:
    def __init__(self):
        self.net = None
        self.transformer = None
        self._initialize_model()

    def _initialize_model(self):
        try:
            self.net = caffe.Net(config.MODEL_DEF, config.PRETRAINED_MODEL, caffe.TEST)
            
            self.transformer = caffe.io.Transformer(
                {'data': self.net.blobs['data'].data.shape})
            self.transformer.set_transpose('data', (2, 0, 1))
            self.transformer.set_mean('data', np.array([104, 117, 123]))
            self.transformer.set_raw_scale('data', 255)
            self.transformer.set_channel_swap('data', (2, 1, 0))
            
            logger.info("Model initialized successfully")
        except Exception as e:
            logger.error("Model initialization failed: %s", str(e))
            raise

    def resize_image(self, data, sz=(256, 256)):
        try:
            im = Image.open(BytesIO(data))
            if im.mode != "RGB":
                im = im.convert('RGB')
            imr = im.resize(sz, resample=Image.BILINEAR)
            
            with BytesIO() as output:
                imr.save(output, format='JPEG')
                return output.getvalue()
        except Exception as e:
            logger.error("Image resize failed: %s", str(e))
            raise
    def predict(self, image_data):
        try:
            img_data_rs = self.resize_image(image_data)
            image = caffe.io.load_image(BytesIO(img_data_rs))
            
            H, W, _ = image.shape
            _, _, h, w = self.net.blobs['data'].data.shape
            h_off = max((H - h) // 2, 0)
            w_off = max((W - w) // 2, 0)
            crop = image[h_off:h_off + h, w_off:w_off + w, :]
            
            transformed_image = self.transformer.preprocess('data', crop)
            transformed_image.shape = (1,) + transformed_image.shape

            input_name = self.net.inputs[0]
            outputs = self.net.forward_all(
                blobs=['prob'],
                **{input_name: transformed_image}
            )
            
            return "{:.10f}".format(float(outputs['prob'][0][1]))
        except Exception as e:
            logger.error("Prediction error: %s", str(e))
            raise

    def predict_from_url(self, image_url):
        try:
            image_io = download_image(image_url)
            image_data = image_io.read()
            return self.predict(image_data)
        except Exception as e:
            raise ValueError("URL处理错误: " + str(e))