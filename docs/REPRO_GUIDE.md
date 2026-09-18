# 快速复现指南(踩坑版)

在任何一台 **24 GB 显存 + 磁盘 ≥100 GB** 的 NVIDIA 机器上从零复现本管线的最短路径。
本文件是实战总结,细节见 `LOCAL_REBUILD.md`(单机适配记录)与原项目各文档。

## 0. 前置条件

| 项 | 要求 | 备注 |
|---|---|---|
| GPU | ≥24 GB,NVIDIA 驱动 ≥570(原生 CUDA 12.8) | 驱动 535 的话 torch 要换 cu121/cu124 并加前向兼容层,别照抄 |
| 网络 | 能通 pypi / github / modelscope | 全被墙时参考原项目 STACK.md 的镜像方案 |
| Python | 3.12(经 uv 自动装) | 3.13 会有部分 wheel 缺 |
| 权限 | 不需要 root | 全部用户态安装 |

**容器用户特别注意:GPU 直通要在启动容器时挂好**
(`--gpus all` 或 `--device /dev/nvidia*` + `NVIDIA_VISIBLE_DEVICES=all`),
否则 `/dev/nvidia*` 不存在,装完一切也白搭——这是本次复现浪费的第一段时间。

## 1. 装基础工具(约 5 分钟)

```bash
mkdir -p repro/tools/bin
curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=$PWD/repro/tools/bin sh
# ffmpeg 静态版(johnvansickle.com)解压进 repro/tools/bin
export PATH=$PWD/repro/tools/bin:$PATH
export UV_PYTHON_INSTALL_DIR=$PWD/repro/tools/python   # 解释器装进项目,勿用默认 ~/.local 或 /tmp
export UV_CACHE_DIR=$PWD/repro/uvcache                  # /tmp 常是 512MB tmpfs,会 No space left
```

## 2. 装 ComfyUI + 依赖(约 30 分钟,看网速)

```bash
git clone --depth 1 --branch v0.34.2 https://github.com/comfyanonymous/ComfyUI
cd ComfyUI/custom_nodes
git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager
git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes
cd ../..
uv venv env --python 3.12
# torch 三件套必须配套 2.9.1 / 0.24.1 / 2.9.1,只 pin torch 会装进不配套的 torchaudio 直接崩
uv pip install torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128
uv pip install -r ComfyUI/requirements.txt
```

## 3. 下载模型 75 GB(瓶颈,约 5 小时)

ModelScope `Comfy-Org/MiniMax-H3` 单连接被限速(~1 MB/s),**必须多连接**。
用 `repro/scripts/fastdl.py`(16 连接/文件 + 断点续传 + sha256 校验),清单在 `scripts/models.json`。
下完校验:`sha256sum -c repro/scripts/models.local.sha256`(注意把里面的根路径 sed 成本机路径)。

## 4. 配置三处路径

1. `extra_model_paths.yaml` → `base_path` 指向本机 `models/`
2. `scripts/start_comfyui.sh` / `svc.sh` 里的项目根路径、PATH(含 ffmpeg)
3. `driver/pipeline.py` 的 `ROOT`

## 5. 启动 + 验证

```bash
bash scripts/svc.sh start                       # 127.0.0.1:8188
./env/bin/python driver/pipeline.py --job jobs/owl_ep01.json --dry-run
./env/bin/python driver/make_character.py --name xxx --frames 3 --desc "..."
./env/bin/python driver/pipeline.py --job jobs/xxx_ep01.json
```

---

## 踩坑点清单(按浪费时间排序)

1. **容器没挂 GPU**:`/dev/nvidia*` 缺失但内核模块在,极易误判"驱动坏了"。先 `ls /dev/nvidia*`。
2. **模型文件尾部 32 MB 缺失**:自写分块下载器 `nparts = size // CHUNK` 忘了向上取整,
   每个文件末尾不足一块的尾巴永远没下载 → SHA_MISMATCH。分块数必须 `ceil`,且装配后校验总大小。
3. **并发下载器互相残杀**:两个下载进程写同一批分块/装配同一文件,导致 "No such file or directory: xxx.part0292"。
   下载前先 `ps` 确认只有一个实例。
4. **旧进程杀不死自己**:`pkill -f "uv pip"` 会匹配到包含同样字符串的当前 shell 自杀。
   用 `pgrep` 拿 pid 再 kill,或模式里加 `[x]` 技巧。
5. **uv 缓存写爆 /tmp**:`No space left on device` → 必须 `UV_CACHE_DIR` 指到大磁盘。
6. **24 GB 3090 跑 243 帧 768×1344 必 OOM**(4090 D 能跑):OOM 点在 MiniMax DiT MLP 的
   int8_linear 激活分配。`--lowvram`、`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 都无效,
   **`--novram`**(权重驻留内存按层流入显存)能跑通,速度约 1/8(单镜头 22 分钟 vs 2.9 分钟)。
   已固化进 `scripts/start_comfyui.sh`。
7. **driver 脚本找不到 ffmpeg**:抽帧阶段 `FileNotFoundError: 'ffmpeg'`。
   ffmpeg 装在项目内的话,把其 bin 加进 PATH(svc.sh 已内置)。
8. **sha256 清单里的硬编码路径**:`scripts/models.sha256` 写死了原机 `/root/video-pipeline`,
   校验前要 sed 成本机路径。
9. **torch 三件套版本配套**:见第 2 步注释,这是原项目 BUILDLOG 里也强调过的坑。
10. **ComfyUI 结果缓存**:相同 prompt+seed 直接回旧产物。测性能必须换 seed;
    失败重跑想复用已生成的视频反而是优点(make_character 重跑抽帧只花了 0.1 分钟)。

## 可选提速(未做)

- 编译 SageAttention 2.2.0(需 nvcc;`pip install nvidia-cuda-nvcc-cu12` 后 `TORCH_CUDA_ARCH_LIST=8.6` 跑 `scripts/build_sage.sh`)
- 多卡:每卡起一个 ComfyUI 实例,按镜头分配
- 短镜头(6s)省一半以上时间
