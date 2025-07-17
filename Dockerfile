FROM bvlc/caffe:cpu

# 1. 修复Caffe Python路径
RUN ln -s /workspace/caffe/python/caffe /usr/local/lib/python2.7/dist-packages/caffe

# 2. 安装依赖
RUN apt-get update && apt-get install -y \
    python-flask \
    python-pil \
    python-numpy \
    && rm -rf /var/lib/apt/lists/*

# 3. 设置工作目录
WORKDIR /workspace
COPY . /workspace/

# 4. 设置Python路径
ENV PYTHONPATH=/workspace:/workspace/caffe/python:$PYTHONPATH

# 5. 安装Python依赖
RUN pip install -r /workspace/requirements.txt

EXPOSE 5000

# 6. 修改启动命令（直接引用wsgi.py）
CMD ["gunicorn", "-b", "0.0.0.0:5000", \
     "--chdir", "/workspace/src", \
     "--pythonpath", "/workspace:/workspace/caffe/python", \
     "wsgi:app"]