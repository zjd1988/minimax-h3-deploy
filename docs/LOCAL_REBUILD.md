# 本机（2× RTX 3090）复现适配记录

原项目跑在火山引擎 4090 D 容器（驱动 535 + CUDA 13 前向兼容层）。
本机为双 RTX 3090（sm_86，24 GB×2）、驱动 570.133.07（原生 CUDA 12.8），
容器内无 root、无 apt、无 nvcc。差异与处理如下。

## 硬件 / 驱动

| 项 | 原机 | 本机 | 处理 |
|---|---|---|---|
| GPU | 1× 4090 D (sm_89) | 2× 3090 (sm_86) | ComfyUI 单卡即可；显存同样 24 GB |
| 驱动 | 535.154.05 + CUDA13 兼容层 | 570.133.07 | **不需要** `LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat` hack，`start_comfyui.sh` 已去掉 |
| torch | 2.9.1+cu130 | **2.9.1+cu128**（cu130 需 ≥580 驱动） | 已装 |
| SageAttention | 2.2.0 本地编译 sm_89 | 未编译（容器无 nvcc） | `start_comfyui.sh` 改为检测到 sageattention 才加 `--use-sage-attention`，否则走 PyTorch SDPA。补编译：`uv pip install nvidia-cuda-nvcc-cu12` 后设 `CUDA_HOME` 再跑 `scripts/build_sage.sh`（已改 `TORCH_CUDA_ARCH_LIST=8.6`） |

## 路径

所有硬编码 `/root/video-pipeline` 已改为 `/workspace/minimax-h3-video-pipeline`
（driver/pipeline.py、scripts/*.sh、extra_model_paths.yaml）。
环境装在 workspace 卷内（`env/`、`ComfyUI/`、`models/`），容器重启不丢。

## 工具链（容器缺的东西，全装在 /workspace/minimax-h3-video-pipeline/repro/tools）

- `bin/uv` 0.12.15、`bin/ffmpeg` 7.0.2 静态版
- `dlenv/`：ModelScope 下载环境（`repro/tools/dlenv/bin/python repro/scripts/fastdl.py` 多连接下载器）
- uv 注意：`UV_CACHE_DIR=/workspace/minimax-h3-video-pipeline/repro/uvcache`（/tmp 只有 512 MB tmpfs 会爆）、
  `UV_PYTHON_INSTALL_DIR=/workspace/minimax-h3-video-pipeline/repro/tools/python`

## 网络

原机的镜像约束（github/pypi 全不通）在本机**不存在**，github / pypi / modelscope 均直连。
但单连接限速 ~190 KB/s～1 MB/s，大文件必须多连接：
`fastdl.py`（模型，16 连接/文件，断点续传 + sha256 校验）与 `repro/scripts/fastdl_wheels.py`（wheel）。
曾踩坑：分块数 `size // CHUNK` 忘了向上取整，文件尾部 32 MB 没下载导致 SHA_MISMATCH，已修。

## 验证状态（全部通过）

- ComfyUI v0.34.2 + Manager + KJNodes：启动 OK（127.0.0.1:8188，`scripts/svc.sh status/start/stop`）
- torch 2.9.1+cu128 / torchvision 0.24.1 / torchaudio 2.9.1：导入 OK，`cuda.is_available()=True`
- 模型 75 GB：18/18 文件 SHA-256 校验通过
- `driver/make_character.py`：owl 角色设定图 3 张 ✅
- `driver/pipeline.py --job jobs/owl_ep01.json`：**6 镜头全部跑通，
  成片 `releases/owl_ep01.mp4`（768×1344 / 24fps / H.264+AAC / 60.8s / 23 MB）** ✅
- `--dry-run` 校验通过

### 3090 上唯一的新坑：OOM

243 帧 768×1344 r2v 在 24 GB 3090 上默认模式必 OOM
（`comfy/ldm/minimax/model.py` MLP 前向 `int8_linear` 分配失败；4090 D 同规格能跑）。
`--lowvram` 无效，`expandable_segments` 无效，最终用 **`--novram`**（权重全留内存、
按层流入显存）跑通。代价是速度：单镜头 ≈22 分钟（4090 D 上 2.9 分钟），一条 6 镜头片
GPU 时间 131 分钟。已固化进 `scripts/start_comfyui.sh`。
提速方向：编译 SageAttention（sm_86）、或 6 秒短镜头、或多卡分镜头并行。
