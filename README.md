# open_nsfw_docker

#### 介绍
基于雅虎开源的nsfw检测模型包装的api服务

#### 软件架构
基于python2.7
caffe1.0.0

#### 安装教程
1. 安装docker环境
2. 执行 `sh build.sh`构建docker镜像
3. 执行 `sh run.sh` 启动镜像

#### 使用说明

##### 检测分值
`curl -X POST -F "file=@test.jpg" http://localhost:5000/score` 
响应：
```json
{
  "filename": "test4.jpg", 
  "score": 0.8056074380874634
}
```

##### 应用健康检查
`curl http://localhost:5000/health`
响应：
```json
{
  "status": "healthy"
}
```

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request