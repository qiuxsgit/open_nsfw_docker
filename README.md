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
`curl -X POST -F "file=@test.jpg" -H "api-key: xxxxxx"  http://localhost:5000/score` 
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

#### Kubernetes 部署

部署清单在 `deploy/k8s/`，CI/CD 在 `Jenkinsfile`，约定与 `douyin-sign` 保持一致：
内网 HTTP registry `192.168.1.103:5000`、namespace `apps`、Traefik 双 Ingress（8801 明文 / 8802 TLS）、
镜像 tag 固定为 `build-<BUILD_NUMBER>-<GIT_SHA>`（禁止 latest）。

| 文件 | 说明 |
| --- | --- |
| `deploy/k8s/deployment.yaml` | 2 副本、滚动更新；image 是占位值，由 Jenkins 注入真实 tag |
| `deploy/k8s/service.yaml` | ClusterIP，端口 5000 |
| `deploy/k8s/ingress.yaml` | Traefik 两个 Ingress（web / websecure），域名 `open-nsfw.k8s.qiuxs.com` |
| `deploy/k8s/secret.example.yaml` | api-key Secret 示例，⚠️ 真实 key 不要提交进 Git |

##### 1. 先创建 api-key Secret（必须）

`src/app/config.py` 在进程启动时读取 `/py_config/password.txt` 作为 api-key，由 Secret 挂载提供：

```bash
printf '你的真实key' > /tmp/password.txt
kubectl create secret generic open-nsfw-apikey -n apps \
  --from-file=password.txt=/tmp/password.txt
shred -u /tmp/password.txt
```

> ⚠️ 这一步不是可选项。密码文件不存在时 `config.PASSWORD` 为 `None`，而鉴权逻辑是
> `request.headers.get('api-key') == config.PASSWORD` —— 不带 `api-key` 头的请求同样拿到 `None`，
> 会被判定为验证通过，`/score` 就变成了裸奔接口。所以 Jenkins 在 Prepare 阶段检查不到该 Secret 会直接终止发布。
>
> 轮换 key 后需要 `kubectl rollout restart deployment/open-nsfw -n apps`，因为 key 只在进程启动时读一次。

##### 2. Jenkins 发布

Job 类型 `Pipeline from SCM`，Script Path = `Jenkinsfile`。前置条件同 douyin-sign：
jenkins 用户可 `sudo -u root docker`、可直接用 `kubectl`（ServiceAccount 只对 `apps` 有权限）、
构建机与各 Kubernetes 节点都把 `192.168.1.103:5000` 配成 insecure registry。

常用参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `USE_PROXY` / `PROXY_URL` | true / `http://127.0.0.1:7897` | 拉 GitHub 代码走代理，等价于本机的 `proxy_on` |
| `BUILD_PROXY_URL` | 空 | `docker build` 内部 apt/pip 用的代理，⚠️ 不能填 127.0.0.1 |
| `IMAGE_SMOKE_TEST` | true | 推送前先在构建机本地跑一遍镜像并真实调用 `/score` |
| `ROLLOUT_TIMEOUT` | 600s | 镜像约 1.7G，节点首次 pull 慢 |
| `ENABLE_INGRESS` | true | 关掉则只保留集群内访问 |

**关于代理**：本仓库在 GitHub 上，拉代码必须走代理，但内网 registry 和 kubectl 绝对不能走代理，
所以流水线只在 `checkout` 这一步用 `withEnv` 局部注入代理，其余阶段环境保持干净，`NO_PROXY` 里也显式排除了内网地址。
有两处是 Jenkinsfile 管不到、需要在机器上配置的：

- Jenkins 为读取本文件做的那次 clone 发生在流水线开始之前 —— 需在
  `Manage Jenkins → System → Global properties → Environment variables` 配置 `http_proxy`/`https_proxy`/`no_proxy`，
  或执行 `git config --global http.https://github.com.proxy http://127.0.0.1:7897`。
- 基础镜像 `bvlc/caffe:cpu` 由 dockerd 拉取 —— 需配置 `/etc/systemd/system/docker.service.d/http-proxy.conf`。

##### 3. 手动发布

```bash
# 镜像必须先在本地注入真实 tag 再 apply，避免集群看到占位镜像而 ImagePullBackOff
kubectl set image -f deploy/k8s/deployment.yaml \
  open-nsfw=192.168.1.103:5000/open-nsfw:build-1-abc1234 \
  --local -o yaml | kubectl apply -n apps -f -
kubectl apply -n apps -f deploy/k8s/service.yaml
kubectl apply -n apps -f deploy/k8s/ingress.yaml
kubectl rollout status deployment/open-nsfw -n apps --timeout=600s
```

##### 4. 访问

```bash
# 集群内
curl -X POST -F "file=@test.jpg" -H "api-key: xxxxxx" \
  http://open-nsfw.apps.svc.cluster.local:5000/score
# 公网
curl https://open-nsfw.k8s.qiuxs.com:8802/health
```

##### 5. 排查与回滚

```bash
kubectl get pods -n apps -l app=open-nsfw -o wide
kubectl logs -n apps -l app=open-nsfw --tail=200
kubectl rollout undo deployment/open-nsfw -n apps
```

几类典型故障：`ImagePullBackOff` 且报 `http: server gave HTTP response to HTTPS client` 是节点 containerd 没配 insecure registry；
长时间 `ContainerCreating` 通常只是节点首次拉大镜像；`OOMKilled` 是因为 gunicorn 每个 worker 各加载一份 caffe 模型，
调小 `GUNICORN_CMD_ARGS` 里的 `--workers` 或调大 memory limit。

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request