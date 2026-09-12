// open_nsfw_docker CI/CD —— 构建镜像 -> 推送 Registry -> 部署到 Kubernetes (namespace: apps)
//
// Job：Pipeline from SCM，Script Path = Jenkinsfile
//
// 前置条件：
//   1) jenkins 用户可用 sudo -u root docker（NOPASSWD 建议）
//   2) jenkins 用户可直接执行 kubectl，且 ServiceAccount 为
//      system:serviceaccount:apps:jenkins-deployer，仅对 apps namespace 有权限
//      —— 因此本文件不配置任何 kubeconfig / token / 证书
//   3) 镜像仓库固定为 192.168.1.103:5000（HTTP、无认证、仅内网可达），需要：
//      - 构建机 /etc/docker/daemon.json 配置 insecure-registries
//      - 每个 Kubernetes 节点的 containerd 也配置该仓库为 insecure，否则 Pod 无法 pull
//   4) 集群里必须已存在 Secret apps/open-nsfw-apikey（key = password.txt），
//      否则 Prepare 阶段直接失败，见 deploy/k8s/secret.example.yaml
//
// 部署镜像始终使用本次构建的唯一 tag：build-${BUILD_NUMBER}-${GIT_SHA}，不使用 latest。
//
// ───────────────── 代理说明（本仓库托管在 GitHub，必须走代理）─────────────────
// 机器上的 `proxy_on` 是 shell 函数（定义在 ~/.zshrc），作用是导出
// http_proxy / https_proxy / all_proxy 三个变量，代理端口为 7890。
// Jenkins 的 sh 步骤用的是非交互 /bin/sh，读不到 zsh 函数，所以这里不调用 proxy_on，
// 而是把等价的环境变量显式注入（地址由 PROXY_URL 参数控制，默认 http://127.0.0.1:7890）。
// 分三种情况：
//
//   A. 拉 GitHub 代码 —— 需要代理。
//      本文件只能控制 `checkout scm` 这一步（withEnv 注入后 git 子进程会继承）。
//      ⚠️ Jenkins 为了读到本 Jenkinsfile 自身做的那次 clone 发生在流水线开始之前，
//         不受本文件控制，必须在 Jenkins 里配置好，二选一：
//           - Manage Jenkins → System → Global properties → Environment variables
//             加 http_proxy / https_proxy / no_proxy
//           - 或 jenkins 用户执行：git config --global http.https://github.com.proxy http://127.0.0.1:7890
//      ⚠️ 若仓库用 SSH 地址(git@github.com)，http_proxy 无效，需在 ~/.ssh/config 配 ProxyCommand。
//
//   B. 访问内网 registry / kubectl 访问 apiserver —— 绝对不能走代理。
//      所以代理只在需要外网的阶段用 withEnv 局部注入，其余阶段环境干净；
//      同时 NO_PROXY 里显式列出 192.168.1.103（老版本 curl 不认 CIDR，只认精确主机）。
//
//   C. docker build 内部的 apt-get / pip —— 需要代理，但不能用 127.0.0.1。
//      构建容器里的 127.0.0.1 是容器自己，必须填宿主机可达地址（docker0 网关
//      172.17.0.1，或构建机局域网 IP）。用 BUILD_PROXY_URL 参数单独指定，
//      留空则不给 docker build 传代理（依赖 dockerd 自身的代理配置）。
//      ⚠️ 基础镜像 bvlc/caffe:cpu 的 pull 由 dockerd 发起，同样不看这里的环境变量，
//         需要配置 /etc/systemd/system/docker.service.d/http-proxy.conf。

// 只在需要外网的步骤上用 withEnv 注入，避免污染 kubectl / 内网 registry 访问
def proxyEnv() {
  // 首次构建时 parameters 可能尚未注册，params.* 为 null，这里回落到与默认值一致的行为
  def useProxy = (params.USE_PROXY == null) ? true : params.USE_PROXY
  if (!useProxy) {
    return []
  }
  def url = ((params.PROXY_URL == null) ? 'http://127.0.0.1:7890' : params.PROXY_URL).trim()
  if (!url) {
    return []
  }
  def noProxy = [
    '127.0.0.1', 'localhost', '::1',
    '192.168.1.103',                                   // 内网镜像仓库，必须直连
    '192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12',   // 内网网段（Go 程序如 kubectl 认 CIDR）
    '.svc', '.svc.cluster.local', '.cluster.local', '.local',
    (params.EXTRA_NO_PROXY ?: '').trim()
  ].findAll { it }.join(',')

  return [
    "http_proxy=${url}",  "HTTP_PROXY=${url}",
    "https_proxy=${url}", "HTTPS_PROXY=${url}",
    "no_proxy=${noProxy}", "NO_PROXY=${noProxy}"
  ]
}

pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    // caffe 镜像大、节点首次 pull 慢，整体超时放宽到 60 分钟
    timeout(time: 60, unit: 'MINUTES')
  }

  parameters {
    booleanParam(
      name: 'USE_PROXY',
      defaultValue: true,
      description: '拉取 GitHub 代码时使用代理（等价于本机的 proxy_on）'
    )
    string(
      name: 'PROXY_URL',
      defaultValue: 'http://127.0.0.1:7890',
      description: '构建机上的 HTTP 代理地址，仅用于 checkout 等需要外网的步骤'
    )
    string(
      name: 'BUILD_PROXY_URL',
      defaultValue: '',
      description: 'docker build 容器内可达的代理地址（如 http://172.17.0.1:7890）。留空则不给 build 传代理；⚠️ 这里不能填 127.0.0.1'
    )
    string(
      name: 'EXTRA_NO_PROXY',
      defaultValue: '',
      description: '追加到 NO_PROXY 的主机/网段，逗号分隔（如 apiserver 域名）'
    )
    string(
      name: 'ROLLOUT_TIMEOUT',
      defaultValue: '600s',
      description: 'kubectl rollout status 超时时间（镜像约 1.7G，节点首次 pull 慢，建议 ≥600s）'
    )
    booleanParam(
      name: 'ENABLE_INGRESS',
      defaultValue: true,
      description: '是否下发 Ingress（公网访问 open-nsfw.k8s.qiuxs.com:8801/8802）'
    )
    booleanParam(
      name: 'IMAGE_SMOKE_TEST',
      defaultValue: true,
      description: '推送前先在构建机本地跑一遍镜像：等 /health 健康，并用容器内 python 调一次 /score'
    )
    booleanParam(
      name: 'SMOKE_TEST',
      defaultValue: false,
      description: '发布成功后从 Jenkins 机器访问 Ingress 的 /health 做冒烟测试（需 Jenkins 能解析该域名）'
    )
    booleanParam(
      name: 'NO_CACHE',
      defaultValue: false,
      description: 'docker build 不使用缓存（模型/依赖没变时不要开，会重跑 apt-get 和 pip）'
    )
    booleanParam(
      name: 'PRUNE_LOCAL_IMAGE',
      defaultValue: false,
      description: '推送成功后删除构建机上的本次镜像 tag（省磁盘，但下次构建缓存会失效）'
    )
  }

  environment {
    APP_NAME       = 'open-nsfw'
    IMAGE_NAME     = 'open-nsfw'
    DEPLOYMENT     = 'open-nsfw'
    CONTAINER      = 'open-nsfw'
    SERVICE        = 'open-nsfw'
    INGRESS        = 'open-nsfw'
    INGRESS_TLS    = 'open-nsfw-tls'
    INGRESS_HOST   = 'open-nsfw.k8s.qiuxs.com'
    CONTAINER_PORT = '5000'
    K8S_DIR        = 'deploy/k8s'
    // api-key Secret：config.py 读 /py_config/password.txt，由该 Secret 挂载提供
    APIKEY_SECRET  = 'open-nsfw-apikey'
    APIKEY_KEY     = 'password.txt'

    // 镜像仓库：内网 HTTP registry，无认证
    IMAGE_REGISTRY = '192.168.1.103:5000'
    // Kubernetes namespace：与 ServiceAccount system:serviceaccount:apps:jenkins-deployer 一致
    K8S_NS         = 'apps'

    // 与原流水线一致：root 身份操作 docker
    DOCKER = 'sudo -u root docker'

    // ⚠️ 参数传进 sh 的两个坑：
    //   1) 参数不落到 environment，sh 里引用会报「未绑定的变量」；
    //   2) 值为空字符串时 Jenkins 干脆不导出该变量，所以 shell 侧仍要用 ${VAR:-}。
    //   布尔参数不能写 ?:（false 会被当假值而回落成默认值），要显式判 null。
    ROLLOUT_TIMEOUT = "${params.ROLLOUT_TIMEOUT ?: '600s'}"
    ENABLE_INGRESS  = "${params.ENABLE_INGRESS == null ? 'true' : params.ENABLE_INGRESS}"
    BUILD_PROXY_URL = "${params.BUILD_PROXY_URL ?: ''}"
    NO_CACHE        = "${params.NO_CACHE == null ? 'false' : params.NO_CACHE}"
  }

  stages {

    stage('Checkout') {
      steps {
        script {
          // 拉 GitHub 代码需要代理：withEnv 注入后，git 插件启动的 git 子进程会继承这些变量
          def pe = proxyEnv()
          if (pe) {
            echo "使用代理拉取代码：${params.PROXY_URL}（NO_PROXY 已排除内网与集群地址）"
          } else {
            echo "未启用代理（USE_PROXY=false 或 PROXY_URL 为空）"
          }
          withEnv(pe) {
            checkout scm
          }

          env.GIT_SHA = sh(script: 'git rev-parse --short HEAD 2>/dev/null || echo dev', returnStdout: true).trim()

          // 唯一镜像 tag：BUILD_NUMBER + Git Commit，禁止 latest
          env.IMAGE_TAG   = "build-${env.BUILD_NUMBER}-${env.GIT_SHA}"
          env.IMAGE_LOCAL = "${env.IMAGE_NAME}:${env.IMAGE_TAG}"

          env.IMAGE_FULL  = "${env.IMAGE_REGISTRY}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"

          echo "Git SHA      : ${env.GIT_SHA}"
          echo "Image tag    : ${env.IMAGE_TAG}"
          echo "Image (push) : ${env.IMAGE_FULL}"
          echo "Namespace    : ${env.K8S_NS}  Deployment: ${env.DEPLOYMENT}"
        }
      }
    }

    stage('Prepare') {
      steps {
        sh '''
          set -eu

          echo "=== 检查 root docker ==="
          ${DOCKER} version

          echo "=== 检查镜像仓库 ${IMAGE_REGISTRY}（HTTP，无认证）==="
          # 注意：本步骤没有注入代理，直连内网 registry
          if ! curl -fsS --noproxy '*' --max-time 5 "http://${IMAGE_REGISTRY}/v2/" >/dev/null; then
            echo "镜像仓库 ${IMAGE_REGISTRY} 不可达或未启用 v2 API"
            echo "请确认：registry 已启动、构建机到该地址网络可通、代理没有劫持内网地址"
            exit 1
          fi
          echo "registry OK"

          echo "=== 检查 kubectl ==="
          kubectl version --client
          echo "当前身份可访问性检查（namespace=${K8S_NS}）："
          kubectl get deployments -n "${K8S_NS}"

          echo "=== 检查 api-key Secret ${APIKEY_SECRET}（namespace=${K8S_NS}）==="
          # ⚠️ 这是安全前置条件，不是可选项：
          #    config.py 读不到 /py_config/password.txt 时 PASSWORD=None，
          #    而 main.py 用 request.headers.get('api-key') == config.PASSWORD 校验，
          #    不带 api-key 头的请求同样得到 None → 判定通过 → /score 变成裸奔接口。
          if ! kubectl get secret "${APIKEY_SECRET}" -n "${K8S_NS}" >/dev/null 2>&1; then
            echo "缺少 Secret ${APIKEY_SECRET}，拒绝发布（否则 /score 会失去鉴权）"
            echo "请先在集群上创建（key 不会进 Git，也不会进 Jenkins 日志）："
            echo "  printf '你的真实key' > /tmp/password.txt"
            echo "  kubectl create secret generic ${APIKEY_SECRET} -n ${K8S_NS} \\\\"
            echo "    --from-file=${APIKEY_KEY}=/tmp/password.txt"
            echo "  shred -u /tmp/password.txt"
            exit 1
          fi
          # 只打印 key 名，不打印 value，避免 api-key 泄漏进构建日志
          SECRET_KEYS="$(kubectl get secret "${APIKEY_SECRET}" -n "${K8S_NS}" \
            -o go-template='{{range $k, $v := .data}}{{$k}}{{"\\n"}}{{end}}')"
          echo "Secret 内包含的 key：${SECRET_KEYS}"
          if ! echo "${SECRET_KEYS}" | grep -qx "${APIKEY_KEY}"; then
            echo "Secret ${APIKEY_SECRET} 里没有 key「${APIKEY_KEY}」，deployment 挂载会失败"
            exit 1
          fi
          echo "Secret OK"

          echo "=== 检查 Kubernetes manifest ==="
          test -f "${K8S_DIR}/deployment.yaml" || { echo "缺少 ${K8S_DIR}/deployment.yaml"; exit 1; }
          test -f "${K8S_DIR}/service.yaml"    || { echo "缺少 ${K8S_DIR}/service.yaml"; exit 1; }
          if [ "${ENABLE_INGRESS}" = "true" ]; then
            test -f "${K8S_DIR}/ingress.yaml"  || { echo "缺少 ${K8S_DIR}/ingress.yaml"; exit 1; }
          fi
          ls -l "${K8S_DIR}"

          echo "=== 检查模型文件（镜像里的模型来自仓库，缺了会在启动时崩）==="
          test -f nsfw_model/deploy.prototxt            || { echo "缺少 nsfw_model/deploy.prototxt"; exit 1; }
          test -f nsfw_model/resnet_50_1by2_nsfw.caffemodel || { echo "缺少 nsfw_model/resnet_50_1by2_nsfw.caffemodel"; exit 1; }
          ls -l nsfw_model
        '''
      }
    }

    stage('Build Image') {
      steps {
        sh '''
          set -eu
          echo "=== 构建镜像 ${IMAGE_FULL} ==="

          # ⚠️ Jenkins 不会把「值为空字符串」的 environment 变量导出给 shell
          #    （BUILD_PROXY_URL 默认就是空），在 set -u 下直接引用会报
          #    「未绑定的变量 / unbound variable」并导致整个阶段失败，
          #    所以这里统一用 ${VAR:-} 的形式取值。
          BUILD_PROXY="${BUILD_PROXY_URL:-}"

          BUILD_ARGS=""
          if [ -n "${BUILD_PROXY}" ]; then
            case "${BUILD_PROXY}" in
              *127.0.0.1*|*localhost*)
                echo "BUILD_PROXY_URL 不能是 127.0.0.1/localhost：构建容器里的回环地址是容器自己。"
                echo "请改成宿主机可达地址，例如 docker0 网关 http://172.17.0.1:7890"
                exit 1
                ;;
            esac
            echo "docker build 使用代理：${BUILD_PROXY}（供镜像内 apt-get / pip 使用）"
            # http_proxy/https_proxy/no_proxy 是 docker 预定义 build-arg，
            # 无需在 Dockerfile 里声明 ARG，也不会写进镜像 history。
            BUILD_ARGS="--build-arg http_proxy=${BUILD_PROXY} \
                        --build-arg https_proxy=${BUILD_PROXY} \
                        --build-arg no_proxy=127.0.0.1,localhost,192.168.1.103"
          else
            echo "未设置 BUILD_PROXY_URL：镜像内的 apt-get / pip 直连"
            echo "（若卡在 apt-get update 或 pip download，就是缺这个代理）"
          fi

          CACHE_ARG=""
          if [ "${NO_CACHE:-false}" = "true" ]; then
            CACHE_ARG="--no-cache"
          fi

          # 基础镜像 bvlc/caffe:cpu 由 dockerd 拉取，走的是 dockerd 的代理配置，
          # 不看这里的 build-arg。首次构建若卡在 pull，请配置：
          #   /etc/systemd/system/docker.service.d/http-proxy.conf
          # shellcheck disable=SC2086
          ${DOCKER} build \
            ${CACHE_ARG} \
            ${BUILD_ARGS} \
            --label "org.opencontainers.image.revision=${GIT_SHA}" \
            --label "org.opencontainers.image.version=${IMAGE_TAG}" \
            -t "${IMAGE_LOCAL}" \
            -t "${IMAGE_FULL}" \
            -f Dockerfile \
            .

          ${DOCKER} images "${IMAGE_NAME}" | head -n 10
        '''
      }
    }

    stage('Image Smoke Test') {
      when {
        expression { return params.IMAGE_SMOKE_TEST }
      }
      steps {
        // 先在构建机本地把镜像跑起来验证，避免把「能构建但起不来」的镜像推上去。
        // 注意：源码里的 src/tests 依赖 caffe 与相对导入(from ..wsgi import app)，
        // 无法在 CI 里直接 python -m unittest 跑通，所以这里用真实容器做端到端验证。
        sh '''
          set -eu

          NAME="open-nsfw-smoke-${BUILD_NUMBER}"
          # 用按构建号固定的路径（而不是 mktemp），这样本阶段的 post always 也能清理掉
          SMOKE_DIR="/tmp/open-nsfw-smoke-${BUILD_NUMBER}"
          SMOKE_KEY="smoke-$(date +%s)-${BUILD_NUMBER}"

          rm -rf "${SMOKE_DIR}"
          mkdir -p "${SMOKE_DIR}"
          chmod 0755 "${SMOKE_DIR}"

          # 临时 api-key 文件，只在本次冒烟测试的容器里用；容器以 uid 10001 运行，所以要可读
          printf '%s' "${SMOKE_KEY}" > "${SMOKE_DIR}/password.txt"
          chmod 0444 "${SMOKE_DIR}/password.txt"

          ${DOCKER} rm -f "${NAME}" >/dev/null 2>&1 || true

          echo "=== 启动测试容器 ${NAME} ==="
          # 端口让 docker 随机分配并只绑到回环，避免和构建机上其它服务冲突。
          # ⚠️ 这里刻意复刻 deploy/k8s/deployment.yaml 的运行方式：
          #    非 root(10001) + 只读根文件系统 + /tmp 可写 + 同一套环境变量，
          #    这样「镜像和 securityContext 不兼容」会在推镜像之前就暴露，
          #    而不是等到集群里 CrashLoopBackOff 再回头查。
          ${DOCKER} run -d --name "${NAME}" \
            -p 127.0.0.1::5000 \
            --user 10001:10001 \
            --read-only \
            --tmpfs /tmp:rw,exec,size=256m \
            --cap-drop ALL \
            --security-opt no-new-privileges \
            -e TZ=Asia/Shanghai \
            -e MODEL_DIR=/workspace/nsfw_model \
            -e PYTHONUNBUFFERED=1 \
            -e PYTHONDONTWRITEBYTECODE=1 \
            -e HOME=/tmp \
            -e MPLCONFIGDIR=/tmp \
            -e GLOG_logtostderr=1 \
            -e OMP_NUM_THREADS=2 \
            -e OPENBLAS_NUM_THREADS=2 \
            -e MKL_NUM_THREADS=2 \
            -e GUNICORN_CMD_ARGS="--workers=1 --timeout=300 --graceful-timeout=30 --worker-tmp-dir=/tmp --access-logfile=- --error-logfile=-" \
            -v "${SMOKE_DIR}/password.txt":/py_config/password.txt:ro \
            "${IMAGE_LOCAL}"

          # docker run -d 返回时容器可能已经崩了。先确认它还活着再取端口，
          # 否则 docker port 报错、PORT 为空，后面 curl 一个残缺 URL，
          # 真正的报错会被这些噪音盖住。
          dump_and_die() {
            echo "❌ $1"
            echo "--- 容器状态 ---"
            ${DOCKER} inspect -f 'ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{.State.Error}}' "${NAME}" 2>&1 || true
            echo "--- docker logs（含 stderr）---"
            ${DOCKER} logs --tail=200 "${NAME}" 2>&1 || true
            echo "----------------------------------------"
            echo "排查提示："
            echo "  * Permission denied / Read-only file system →"
            echo "    镜像与降权配置不兼容（--user 10001 / --read-only），"
            echo "    deploy/k8s/deployment.yaml 的 securityContext 要同步放宽。"
            echo "    对照验证：去掉 --user/--read-only 再跑一次，能起来就是这个原因："
            echo "      sudo docker run --rm -v /tmp/pw.txt:/py_config/password.txt:ro ${IMAGE_LOCAL}"
            echo "  * Worker failed to boot →"
            echo "    gunicorn 起 worker 时导入应用失败，日志里往上找 Traceback，"
            echo "    多半是 caffe 加载模型失败（模型文件缺失/不可读）。"
            echo "  * exec format error / no such file →"
            echo "    镜像构建有问题，检查 Dockerfile 的 CMD 与 /workspace 内容。"
            exit 1
          }

          if [ "$(${DOCKER} inspect -f '{{.State.Running}}' "${NAME}" 2>/dev/null || echo false)" != "true" ]; then
            dump_and_die "容器启动后立即退出"
          fi

          PORT="$(${DOCKER} port "${NAME}" 5000/tcp 2>/dev/null | head -n 1 | sed 's/.*://')"
          if [ -z "${PORT}" ]; then
            dump_and_die "取不到映射端口（容器可能正在退出）"
          fi
          echo "容器运行中，本地端口：${PORT}"

          echo "=== 等待 /health（模型加载需要时间，最多 180s）==="
          ok=0
          i=1
          while [ "${i}" -le 60 ]; do
            if curl -fsS --noproxy '*' --max-time 5 "http://127.0.0.1:${PORT}/health" 2>/dev/null | grep -q healthy; then
              echo "health OK (try ${i})"
              ok=1
              break
            fi
            if [ "$(${DOCKER} inspect -f '{{.State.Running}}' "${NAME}" 2>/dev/null || echo false)" != "true" ]; then
              dump_and_die "等待 /health 期间容器退出"
            fi
            i=$((i + 1))
            sleep 3
          done
          if [ "${ok}" != "1" ]; then
            dump_and_die "/health 在 180s 内始终不健康"
          fi

          echo "=== 用容器内的 python 调一次 /score（验证模型真的能推理）==="
          # 在容器内发请求：镜像里已有 PIL / requests，不依赖构建机的 python 环境；
          # heredoc 用引号包住，避免 shell 展开 python 代码里的 $ 和引号
          ${DOCKER} exec -i -e SMOKE_KEY="${SMOKE_KEY}" "${NAME}" python - <<'PY'
import os
from io import BytesIO

import requests
from PIL import Image

buf = BytesIO()
Image.new('RGB', (256, 256), (128, 128, 128)).save(buf, 'JPEG')

resp = requests.post(
    'http://127.0.0.1:5000/score',
    files={'file': ('smoke.jpg', buf.getvalue())},
    headers={'api-key': os.environ['SMOKE_KEY']},
    timeout=120,
)
print('HTTP %s %s' % (resp.status_code, resp.text))

body = resp.json()
assert resp.status_code == 200, 'unexpected status'
assert 'score' in body, 'no score in response: %s' % resp.text
assert 0.0 <= float(body['score']) <= 1.0, 'score out of range: %s' % body['score']
print('score smoke OK: %s' % body['score'])

# 反向验证鉴权确实生效：错误 key 必须拿不到 score
bad = requests.post(
    'http://127.0.0.1:5000/score',
    files={'file': ('smoke.jpg', buf.getvalue())},
    headers={'api-key': 'definitely-wrong-key'},
    timeout=60,
)
assert 'score' not in bad.json(), 'api-key check is broken: %s' % bad.text
print('auth smoke OK')
PY

          echo "✅ 镜像冒烟测试通过"
        '''
      }
      post {
        always {
          sh '''
            set -eu
            ${DOCKER} rm -f "open-nsfw-smoke-${BUILD_NUMBER}" >/dev/null 2>&1 || true
            # 临时 api-key 文件必须删掉，不要留在构建机的 /tmp 里
            rm -rf "/tmp/open-nsfw-smoke-${BUILD_NUMBER}"
          '''
        }
      }
    }

    stage('Push Image') {
      steps {
        // 内网 registry 无认证，不需要 docker login，也没有任何凭据需要处理
        sh '''
          set -eu
          echo "=== 推送 ${IMAGE_FULL} ==="
          ${DOCKER} push "${IMAGE_FULL}"

          echo "=== 校验仓库中已存在该 tag ==="
          curl -fsS --noproxy '*' --max-time 5 "http://${IMAGE_REGISTRY}/v2/${IMAGE_NAME}/tags/list" || true
        '''
      }
    }

    stage('Deploy to Kubernetes') {
      steps {
        sh '''
          set -eu

          NS="${K8S_NS}"

          # 诊断输出脱敏：屏蔽 token / password / secret / api-key / authorization 的取值
          redact() {
            sed -E \
              -e 's/([Aa]uthorization|AUTHORIZATION)[[:space:]]*[:=].*/\\1: ****REDACTED****/g' \
              -e 's/(([Tt]oken|TOKEN|[Pp]assword|PASSWORD|[Ss]ecret|SECRET|[Aa]pi[_-]?[Kk]ey|API[_-]?KEY)[A-Za-z0-9_-]*[[:space:]]*[:=][[:space:]]*)[^[:space:]]+/\\1****REDACTED****/g'
          }

          diagnose() {
            echo ""
            echo "=================== 发布失败诊断（namespace=${NS}）==================="

            echo "--- kubectl get deployment -n ${NS} ---"
            kubectl get deployment -n "${NS}" || true

            echo ""
            echo "--- kubectl get pods -n ${NS} -o wide ---"
            kubectl get pods -n "${NS}" -o wide || true

            echo ""
            echo "--- kubectl describe deployment ${DEPLOYMENT} -n ${NS} ---"
            kubectl describe deployment "${DEPLOYMENT}" -n "${NS}" 2>&1 | redact || true

            echo ""
            echo "--- kubectl get rs -n ${NS} -l app=${APP_NAME} ---"
            kubectl get rs -n "${NS}" -l app="${APP_NAME}" -o wide || true

            # 自动定位异常 Pod：READY 不满 或 STATUS != Running；找不到则退回全部 Pod
            PODS="$(kubectl get pods -n "${NS}" -l app="${APP_NAME}" --no-headers 2>/dev/null \
                    | awk '{ split($2, r, "/"); if (r[1] != r[2] || $3 != "Running") print $1 }' \
                    | head -n 5)" || true
            if [ -z "${PODS}" ]; then
              echo ""
              echo "（没有找到异常 Pod，回退输出全部 app=${APP_NAME} 的 Pod）"
              PODS="$(kubectl get pods -n "${NS}" -l app="${APP_NAME}" --no-headers 2>/dev/null \
                      | awk '{ print $1 }' | head -n 5)" || true
            fi

            if [ -z "${PODS}" ]; then
              echo ""
              echo "--- namespace ${NS} 中不存在 app=${APP_NAME} 的 Pod（可能是调度失败或 Deployment 未创建 Pod）---"
            else
              echo ""
              echo "--- 异常 Pod 详情（describe，已脱敏）---"
              for p in ${PODS}; do
                echo ">>> kubectl describe pod ${p} -n ${NS}"
                kubectl describe pod "${p}" -n "${NS}" 2>&1 | redact || true
                echo ""
              done

              echo "--- 异常 Pod 日志（tail 100，已脱敏）---"
              for p in ${PODS}; do
                echo ">>> kubectl logs ${p} -n ${NS} --tail=100"
                kubectl logs -n "${NS}" "${p}" --all-containers --tail=100 2>&1 | redact || true
                echo ">>> kubectl logs ${p} -n ${NS} --previous --tail=50（上一次崩溃的容器）"
                kubectl logs -n "${NS}" "${p}" --all-containers --tail=50 --previous 2>/dev/null | redact || true
                echo ""
              done
            fi

            echo "--- kubectl get events -n ${NS} --sort-by=.lastTimestamp | tail -50 ---"
            kubectl get events -n "${NS}" --sort-by='.lastTimestamp' 2>/dev/null | tail -n 50 | redact || true

            echo "=================== 诊断结束 ==================="
            echo "常见原因："
            echo "  * ImagePullBackOff / HTTP response to HTTPS client → 节点 containerd 未把 ${IMAGE_REGISTRY} 配为 insecure"
            echo "  * 长时间 ContainerCreating → 节点首次拉 1.7G 的 caffe 镜像，属正常，调大 ROLLOUT_TIMEOUT"
            echo "  * CrashLoopBackOff + Permission denied → deployment.yaml 的 runAsUser/readOnlyRootFilesystem 与镜像不兼容"
            echo "  * MountVolume failed (secret ${APIKEY_SECRET}) → Secret 被删或 key 名不是 ${APIKEY_KEY}"
            echo "  * OOMKilled → gunicorn 每个 worker 各加载一份模型，调小 GUNICORN_CMD_ARGS 的 --workers 或调大 memory limit"
            echo "如需回滚到上一个可用版本，请手动执行："
            echo "  kubectl rollout undo deployment/${DEPLOYMENT} -n ${NS}"
          }

          echo "=== 1/3 下发 Deployment（镜像在本地注入后再 apply）==="
          echo "image = ${IMAGE_FULL}"
          # kubectl set image --local 只在 Jenkins 本地改 YAML，不访问 apiserver。
          # 这样 Kubernetes 第一次看到 Deployment 时镜像就是本次构建的唯一 tag，
          # 不会先创建 PLACEHOLDER 镜像的 Deployment 而产生 ErrImagePull / ImagePullBackOff。
          kubectl set image \
            -f "${K8S_DIR}/deployment.yaml" \
            "${CONTAINER}=${IMAGE_FULL}" \
            --local -o yaml \
            | kubectl apply -n "${NS}" -f -

          echo ""
          echo "=== 2/3 下发 Service / Ingress 并记录发布来源 ==="
          kubectl apply -n "${NS}" -f "${K8S_DIR}/service.yaml"
          if [ "${ENABLE_INGRESS}" = "true" ]; then
            kubectl apply -n "${NS}" -f "${K8S_DIR}/ingress.yaml"
          else
            echo "ENABLE_INGRESS=false，跳过 ingress.yaml"
          fi

          # 发布记录：kubectl rollout history 可以看到是哪次构建、哪个 commit、哪个镜像
          kubectl annotate deployment/"${DEPLOYMENT}" -n "${NS}" \
            kubernetes.io/change-cause="jenkins build ${BUILD_NUMBER} commit ${GIT_SHA} image ${IMAGE_FULL}" \
            --overwrite >/dev/null

          echo ""
          echo "=== 3/3 等待滚动发布完成（timeout=${ROLLOUT_TIMEOUT}）==="
          if kubectl rollout status deployment/"${DEPLOYMENT}" -n "${NS}" --timeout="${ROLLOUT_TIMEOUT}"; then
            echo "✅ rollout 成功"
          else
            echo "❌ rollout 失败或超时"
            diagnose
            exit 1
          fi
        '''
      }
    }

    stage('Verify') {
      steps {
        sh '''
          set -eu
          NS="${K8S_NS}"

          echo "=== kubectl get deployment ${DEPLOYMENT} -n ${NS} ==="
          kubectl get deployment "${DEPLOYMENT}" -n "${NS}" -o wide

          echo ""
          echo "=== kubectl get pods -l app=${APP_NAME} -n ${NS} -o wide ==="
          kubectl get pods -l app="${APP_NAME}" -n "${NS}" -o wide

          echo ""
          echo "=== kubectl get svc ${SERVICE} -n ${NS} ==="
          kubectl get svc "${SERVICE}" -n "${NS}"

          if [ "${ENABLE_INGRESS}" = "true" ]; then
            echo ""
            echo "=== kubectl get ingress -n ${NS} ==="
            kubectl get ingress "${INGRESS}" -n "${NS}"
            kubectl get ingress "${INGRESS_TLS}" -n "${NS}"
          fi

          echo ""
          echo "=== 实际运行镜像 ==="
          kubectl get deployment "${DEPLOYMENT}" -n "${NS}" \
            -o jsonpath='{.spec.template.spec.containers[*].name}{"="}{.spec.template.spec.containers[*].image}{"\\n"}'
        '''
      }
    }

    stage('Smoke Test') {
      when {
        expression { return params.SMOKE_TEST && params.ENABLE_INGRESS }
      }
      steps {
        sh '''
          set -eu
          # 只测 /health：/score 需要 api-key，不把 key 取到 Jenkins 日志所在的机器上
          URL="http://${INGRESS_HOST}:8801/health"
          echo "Checking ${URL} ..."
          ok=0
          i=1
          while [ "${i}" -le 10 ]; do
            if curl -fsS --noproxy '*' --max-time 5 "${URL}"; then
              echo
              echo "Smoke OK (try ${i})"
              ok=1
              break
            fi
            echo "wait ingress... ${i}"
            i=$((i + 1))
            sleep 3
          done
          if [ "${ok}" != "1" ]; then
            echo "冒烟测试失败：${URL} 不可达"
            echo "（Pod 已通过 readinessProbe，问题多半在 DNS / Traefik 路由，请检查 Ingress）"
            kubectl describe ingress "${INGRESS}" -n "${K8S_NS}" || true
            exit 1
          fi
        '''
      }
    }
  }

  post {
    always {
      script {
        if (params.PRUNE_LOCAL_IMAGE && env.IMAGE_LOCAL) {
          sh '''
            set -eu
            echo "=== 清理构建机本地镜像 tag（镜像已在 registry 中）==="
            ${DOCKER} rmi "${IMAGE_LOCAL}" "${IMAGE_FULL}" >/dev/null 2>&1 || true
            ${DOCKER} images "${IMAGE_NAME}" | head -n 10 || true
          '''
        }
      }
    }
    success {
      echo """✅ 发布成功
  image      : ${env.IMAGE_FULL}
  namespace  : ${env.K8S_NS}
  deployment : ${env.DEPLOYMENT}
  集群内访问 : http://${env.SERVICE}.${env.K8S_NS}.svc.cluster.local:${env.CONTAINER_PORT}/health
  公网访问   : http://${env.INGRESS_HOST}:8801/  |  https://${env.INGRESS_HOST}:8802/
  打分示例   : curl -X POST -F "file=@test.jpg" -H "api-key: <见 Secret ${env.APIKEY_SECRET}>" \\
                 https://${env.INGRESS_HOST}:8802/score"""
    }
    failure {
      echo """❌ 发布失败。可在有 kubectl 的机器上继续排查：
  kubectl get pods -n ${env.K8S_NS} -l app=${env.APP_NAME} -o wide
  kubectl describe deployment ${env.DEPLOYMENT} -n ${env.K8S_NS}
  kubectl logs -n ${env.K8S_NS} -l app=${env.APP_NAME} --tail=200
  kubectl rollout undo deployment/${env.DEPLOYMENT} -n ${env.K8S_NS}   # 回滚"""
    }
  }
}
