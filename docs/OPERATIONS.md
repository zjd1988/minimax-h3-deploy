# 操作说明

日常怎么开、怎么关、怎么排错、怎么恢复。
**创作流程（造角色 → 写分镜 → 跑 → 改）看 [PRODUCTION.md](PRODUCTION.md)。**

---

## 连接

```bash
ssh caoyang_lsem_dev01
cd /root/video-pipeline
```

想用 ComfyUI 网页界面，在**你的 Mac** 上开隧道：

```bash
ssh -N -L 8188:127.0.0.1:8188 caoyang_lsem_dev01
```

然后浏览器开 `http://localhost:8188`。
ComfyUI 只监听 `127.0.0.1`，**不对外暴露端口**，必须走隧道。

---

## 服务管理

本容器 **PID 1 是平台的 supervisord，没有 systemd**，所以用 `svc.sh` 管：

```bash
bash scripts/svc.sh status          # 看状态（默认动作）
bash scripts/svc.sh start           # 起 ComfyUI + pipeline watch
bash scripts/svc.sh stop            # 全停
bash scripts/svc.sh restart         # 重启
bash scripts/svc.sh start-comfyui   # 只起 ComfyUI
bash scripts/svc.sh stop-pipeline   # 只停 watch（ComfyUI 继续跑）
```

`status` 输出示例：

```
  comfyui    运行中 pid=1736082
  pipeline   已停止
  API        可达
  GPU        15595 MiB, 100 %
```

**启动要等**：ComfyUI 起来后第一次生成要加载 46 GB 权重，
`start` 会轮询 API 最多 450 秒。API 可达 ≠ 模型已加载。

> `scripts/comfyui.service` 和 `vidpipe.service` 是给日后迁到真实 VM 用的 systemd 单元，
> 在这个容器里用不上。

---

## 两种跑法

### 手动跑（推荐，可控）

```bash
python driver/pipeline.py --job jobs/owl_ep01.json --dry-run   # 先空跑校验
python driver/pipeline.py --job jobs/owl_ep01.json             # 正式跑
```

（`python` 指 `/root/miniconda3/bin/python`，或用 venv 里的 `env/bin/python`，两个都行）

### 常驻监视

```bash
bash scripts/svc.sh start-pipeline
```

之后往 `jobs/` 里扔 `.json`，20 秒内自动开跑。已出成片的 job 会跳过。

---

## 目录约定

```
assets/     角色设定图 + <角色>.json（角色档案）
jobs/       <id>.json 分镜定义
            <id>.manifest.json 运行状态（自动生成，别手改）
outputs/    <job_id>/ 下按镜头存的素材
releases/   <id>.mp4 拼好的成片
logs/       comfyui.log / pipeline_<id>.log / *.pid
models/     75 GB 权重（extra_model_paths.yaml 指向这里）
legal/      MiniMax H3 许可原文
docs/       文档
ComfyUI/input/   参考图和上一镜头视频必须放这里，LoadImage/LoadVideo 只认这个目录
```

---

## 排错

### 症状：`torch.cuda.is_available()` 是 False，日志说 driver too old

```
NVIDIA driver on your system is too old (found version 12020)
```

**原因**：没设 `LD_LIBRARY_PATH` 指向 CUDA 前向兼容层。
内核驱动是 535，但镜像里有 580 的用户态兼容库。

**解法**：任何跑 torch 的命令前都要

```bash
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
```

`scripts/start_comfyui.sh` 里已内置。自己写脚本时别忘了。

### 症状：生成 15 秒就"完成"了，产物是旧的

**原因**：ComfyUI 有结果缓存，相同提示词 + 相同种子直接返回上次产物。

**解法**：换 `seed`。job 里每个镜头都有独立 seed，改一下重跑。

### 症状：某个镜头一直不结束

看进度：

```bash
tail -c 2000 logs/comfyui.log | tr '\r' '\n' | grep -oE '[0-9]+%\|[^|]*\| *[0-9]+/[0-9]+ \[[^]]*\]' | tail -1
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
```

GPU 利用率 100% = 正常在跑，10 秒竖屏要 3–4 分钟。
GPU 0% 且进度条不动超过 5 分钟 = 可能卡住，看 `logs/comfyui.log` 尾部。

### 症状：pipeline 报某镜头失败

`pipeline.py` 默认重试 2 次（`--retries` 可调）。三次都失败会抛出并停在那个镜头。
manifest 里会记 `last_error`。修完提示词后直接重跑同一条命令，
**已完成的镜头会跳过，只从失败那个继续**。

### 症状：`pkill -f "xxx"` 把自己的 SSH 会话杀了

**原因**：`pkill -f` 匹配完整命令行，而你那条 `ssh 'bash -c ...'` 的命令行里
**包含了你要匹配的字符串本身**，所以把自己也杀了。

**解法**：用括号打断字面匹配：

```bash
pkill -f "ComfyUI/mai[n].py"      # 不会匹配到自己
```

这个坑在搭建过程中踩了两次，见 [BUILDLOG.md](BUILDLOG.md)。

---

## 恢复：中断了怎么办

**直接重跑同一条命令。**

```bash
python driver/pipeline.py --job jobs/owl_ep01.json
```

`pipeline.py` 拿到 `prompt_id` 就立刻写 manifest（原子替换），所以：

- 已完成的镜头 → 跳过（实测重跑 6 镜头的 job 用时 0.23 秒，零 GPU 消耗）
- 已提交但没取回的镜头 → **只查状态，不重复提交**（一个镜头 3.7 分钟 GPU，重复提交是纯浪费）
- 没开始的镜头 → 正常跑

**不要手动删 manifest 来"重来"**，那会丢掉所有已完成镜头的记录。
要重做用 `--redo`：

```bash
python driver/pipeline.py --job jobs/owl_ep01.json --redo s03    # s03 及下游
python driver/pipeline.py --job jobs/owl_ep01.json --redo all    # 整条
```

---

## 日常检查

```bash
bash scripts/svc.sh status              # 服务
df -h /                                 # 磁盘（当前 132G/394G）
free -g                                 # 内存（跑生成时会吃到 40G+）
ls -lh releases/                        # 成片
tail -20 logs/pipeline_<job>.log        # 某个 job 的进度
```

---

## 清理

素材增长很慢（每天 10 条片子约 300 MB），一般不用管。真要清：

```bash
# 清掉已拼进成片的镜头素材（成片在 releases/ 里，是独立文件）
rm -rf outputs/<job_id>/

# 清 ComfyUI/input/ 里堆积的中间视频（衔接用的上一镜头副本）
ls ComfyUI/input/*.mp4
```

**别删** `models/`（75 GB，重下要 1 小时）、`env/`、`assets/`（角色设定图）。

---

## 推送改动到 GitHub

**服务器连不上 GitHub**（见 [STACK.md](STACK.md) 的网络约束表），
所以推送必须走「服务器打 bundle → Mac 上推」两步。

### 服务器上：提交并打包

```bash
cd /root/video-pipeline
git add -A && git commit -m "改了什么"
bash scripts/sync.sh                    # 生成 /tmp/video-pipeline.bundle
```

### Mac 上：拉取 bundle 并推送

```bash
scp caoyang_lsem_dev01:/tmp/video-pipeline.bundle /tmp/
cd ~/path/to/minimax-h3-video-pipeline  # 本地克隆
git pull /tmp/video-pipeline.bundle main   # 分支名以 sync.sh 输出为准
git push
```

首次在 Mac 上建本地克隆：

```bash
scp caoyang_lsem_dev01:/tmp/video-pipeline.bundle /tmp/
git clone https://github.com/qingguang0309/minimax-h3-video-pipeline.git
```

> 为什么不在服务器上配 remote：`github.com` 从这台机器完全不通（超时，非 403），
> 配了也推不动。bundle 是 git 官方的离线传输格式，完整保留提交历史。
