# 技术栈

每一层选了什么、为什么选它、从哪拿的。**所有版本号都是实机跑通的版本，不是推荐值。**

---

## 硬件（火山引擎 ML Platform 开发容器）

| 项 | 配置 |
|---|---|
| GPU | NVIDIA **RTX 4090 D**，24 GB 显存（可用 23.6 GB），算力 sm_89 (Ada) |
| CPU | Intel Xeon Platinum 8457C，**容器实配 20 vCPU**（宿主 180 线程，在线 0–19） |
| 内存 | **78 GB**，无 swap |
| 磁盘 | 394 GB 工作卷（overlay / `/dev/vdg`） |
| 共享内存 | `/dev/shm` 55 GB |

注意：容器透传宿主机的 `loadavg`，`uptime` 看到的高负载不代表你自己的负载。
判断自己是否在跑，用 `nvidia-smi` 和 `ps` 看 R 状态进程。

---

## CUDA：一层需要特别说明的兼容层

| 项 | 值 |
|---|---|
| 内核驱动模块 | **535.154.05**（对应 CUDA 12.2） |
| CUDA Toolkit | 13.0（nvcc V13.0.88） |
| **前向兼容层** | `/usr/local/cuda-13.0/compat/libcuda.so.580.126.20` |
| 实测驱动 API | `cuDriverGetVersion()` → **13000 = CUDA 13.0** |

镜像里装了 NVIDIA 的 **CUDA 前向兼容包**，用户态驱动是 580.126.20，
所以内核模块虽是 535，**CUDA 13 / cu130 完全可用**。

**但必须显式指定库路径：**

```bash
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
```

不设的话，`ldconfig` 会解析到 `/usr/lib/x86_64-linux-gnu/libcuda.so.1`（真 535），
torch 报 `NVIDIA driver on your system is too old (found version 12020)`，
`torch.cuda.is_available()` 返回 `False`。

这条已固化进 `scripts/start_comfyui.sh`。**编译 CUDA 扩展时同样需要。**

---

## 软件栈

| 层 | 选择 | 版本 | 来源 |
|---|---|---|---|
| OS | Ubuntu | 24.04.4 LTS (Noble) | 平台镜像 |
| Python | CPython | **3.12.1** | uv venv（基于 miniconda3） |
| 深度学习 | **PyTorch** | **2.9.1+cu130** | `mirror.sjtu.edu.cn/pytorch-wheels/cu130` |
| | torchvision | 0.24.1+cu130 | 同上 |
| | torchaudio | 2.9.1+cu130 | 同上 |
| 推理引擎 | **ComfyUI** | **v0.34.2** | `gitcode.com/gh_mirrors/co/ComfyUI` |
| 自定义节点 | ComfyUI-Manager | HEAD | `gitcode.com/gh_mirrors/co/ComfyUI-Manager` |
| | ComfyUI-KJNodes | HEAD | `gitcode.com/gh_mirrors/co/ComfyUI-KJNodes` |
| 注意力加速 | **SageAttention** | **2.2.0**（本地编译 sm_89） | `gitcode.com/gh_mirrors/sa/SageAttention` |
| 后期 | ffmpeg | 6.1.1 | apt |
| 下载 | aria2 | 1.37.0 | apt |
| 包管理 | uv | 0.12.2 | miniconda3 自带 |

**torch 三件套必须版本配套**（2.9.1 / 0.24.1 / 2.9.1）。
只 pin torch 的话解析器会给 torchaudio 装最新的 2.11.0，
ABI 不匹配，ComfyUI 启动即崩 `undefined symbol: torch_library_impl`。

---

## 模型：MiniMax-H3

来自 ModelScope `Comfy-Org/MiniMax-H3`（全仓 438.6 GB / 31 文件，我们取 **75.23 GB / 18 文件**）。

| 文件 | 体积 | 作用 |
|---|---|---|
| `diffusion_models/minimax_h3_ref2va_pruned_int8_convrot` | 19.53 GB | **Ref2VA** 主力：参考图驱动，保角色一致性 |
| `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot` | 19.53 GB | **FL2VA**：文生视频 / 首尾帧 |
| `text_encoders/qwen3vl_32b_minimax_h3_int8_convrot` | 25.28 GB | 文本编码器（Qwen3-VL-32B，Apache 2.0） |
| `vae/minimax_h3_video_vae_fp16` | 4.85 GB | 视频 VAE |
| `vae/minimax_h3_audio_vae_fp32` | 0.56 GB | **音频 VAE**（H3 音画一体的关键） |
| `loras/minimax_h3_ref2v_turbo_4step_v0.1` | 1.82 GB | Ref2VA 4 步加速 |
| `loras/minimax_h3_fl2v_turbo_8step_v1.0` | 1.82 GB | FL2VA 8 步加速 |
| `loras/minimax_h3_fl2v_turbo_4step_v1.0_768p` | 1.82 GB | FL2VA 4 步加速（未测） |
| `embeddings/minimaxh3_*` ×10 | 11 MB | 运镜特效（子弹时间/螺旋上升/四季等，未测） |

校验：`sha256sum -c scripts/models.sha256`，实测 18/18 通过。

### 为什么选 int8_convrot 而不是 nvfp4_awq

ComfyUI 启动日志会打印本机支持的算子：

```
Native ops:   float8_e5m2, float8_e4m3fn, asym_w4a8_int8, convrot_w4a4, int8_tensorwise
Emulated ops: mxfp8, nvfp4
```

`convrot_w4a4` / `int8_tensorwise` 走**原生 kernel**，`nvfp4` 走**模拟路径**。
官方模板默认给的是 `nvfp4_awq` 编码器——在这台机器上会落进模拟路径。
cu130 + int8_convrot 才是这台机器的正解。

### 显存怎么装得下

编码器 25.9 GB + DiT 20.0 GB = 46 GB，24 GB 显存显然装不下。
ComfyUI 用 **dynamic VRAM loading** 分批调度，把权重放在 78 GB 内存里按需换入。
实测生产设置下显存只占 15.6 GB、GPU 利用率 100%——**没成为瓶颈**。

---

## 网络：这台机器的硬约束

| 目标 | 状态 | 替代方案 |
|---|---|---|
| github.com / raw.githubusercontent / ghproxy | ❌ **完全不通** | `gitcode.com/gh_mirrors/...` |
| download.pytorch.org | ❌ HTTP 403 | `mirror.sjtu.edu.cn/pytorch-wheels/cu130`（PEP 503 索引） |
| huggingface.co | ❌ 不通 | `hf-mirror.com` |
| pypi.org | ⚠️ 数据异常 | volces / 阿里 / 清华 |
| modelscope.cn | ✅ 通 | 单线程 0.65 MB/s，**必须多连接** |

**pypi 镜像同步进度不一致**：volces 快（1.6 MB/s）但滞后
（`comfyui-workflow-templates` 只到 0.11.17，ComfyUI v0.34.2 要 0.11.50），
装 ComfyUI 依赖必须用**阿里或清华**。

**uv 跨多索引要加 `--index-strategy unsafe-best-match`**，
否则 uv 只认第一个含该包名的索引，会报 "no version of torch==2.9.1+cu130"。

---

## 自研代码

```
driver/
  wf.py               统一工作流构建器（t2v / r2v / cont 三种镜头）
  pipeline.py         编排器：队列 + manifest 幂等 + 自动衔接 + 拼接
  make_character.py   角色设定图生成器
  bench*.py           各路径的单独基准脚本（保留作调试用）
scripts/
  start_comfyui.sh    启动（内含 LD_LIBRARY_PATH）
  svc.sh              服务管理（nohup + pidfile）
  build_sage.sh       SageAttention 编译
  aria2.list          模型下载清单（含 SHA-256）
  *.service           systemd 单元（迁到真实 VM 时用）
```

**本容器 PID 1 是平台的 supervisord，没有 systemd**，
且 `supervisord.conf` 无 `[include]` 段——改它有搞挂 sshd / code-server 的风险。
所以服务用 `nohup + pidfile` 自管（`scripts/svc.sh`），
`.service` 文件留作日后迁移到真实 VM 的参考。
