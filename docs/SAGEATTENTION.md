# SageAttention 编译与提速结果

日期：2026-09-02

## 为什么要自己编译

官方只在 GitHub releases 发预编译 wheel，本机 **GitHub 完全不通**。
pypi 上的 `sageattention` 最高只到 **1.0.6**（纯 Triton 实现，`py3-none-any.whl`，没有 CUDA kernel）。
带 CUDA kernel 的 2.x 只有源码分发，所以必须本地编译。

## 获取与编译

源码走 gitcode 的 GitHub 镜像（`gh_mirrors/sag/...` 是 Windows 分支，别用错）：

```bash
git clone --depth 1 --branch v2.2.0 https://gitcode.com/gh_mirrors/sa/SageAttention.git build_sage
```

编译脚本：`scripts/build_sage.sh`。关键点：

- `TORCH_CUDA_ARCH_LIST=8.9` —— **只编 Ada（RTX 4090 D）**。不设的话会编全架构，时间翻好几倍。
- `--no-build-isolation` —— 必须。否则 pip 会在隔离环境里重装一份 torch（几个 GB）。
- `LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat` —— 和跑推理时一样，编译期也要。
- `MAX_JOBS=12` —— 容器只有 20 核在线，留余量。

结果：**2 分 33 秒**墙钟（11 分 55 秒 CPU 时间，12 路并行）。产物：

```
sageattention/_qattn_sm89.cpython-312-x86_64-linux-gnu.so   24.7 MB   ← Ada kernel
sageattention/_qattn_sm80.cpython-312-x86_64-linux-gnu.so   17.8 MB
sageattention/_fused.cpython-312-x86_64-linux-gnu.so        10.8 MB
```

nvcc 13.0 编译 SageAttention 2.2.0 **没有出现兼容问题**（该版本发布早于 CUDA 13，原本担心会有）。

## 算子级验证

B=2, H=16, N=4096, D=128, fp16：

| | 耗时 |
|---|---|
| PyTorch SDPA | 2.06 ms |
| SageAttention | 0.99 ms |
| **加速比** | **2.09×** |

相对误差 **3.8%** —— INT8 量化注意力的正常水平，属于设计上的精度/速度取舍。

## 端到端实测（768×1344 / 10.1s / 243 帧 / 8 步 turbo）

| | 采样速度 | 总耗时（热启动） |
|---|---|---|
| 基线（PyTorch attention） | 62.85 s/步 | **557 s（9.3 分钟）** |
| **开 SageAttention** | **28.90 s/步** | **280 s（4.7 分钟）** |
| **提速** | **2.17×** | **1.99×** |

产物规格不变：768×1344 / 24fps / H.264 + AAC 立体声。

## 启用方式

已写进 `scripts/start_comfyui.sh` 的 `--use-sage-attention`。
启动日志出现 `Using sage attention` 即为生效。

## 踩到的坑

**ComfyUI 有结果缓存。** 相同提示词 + 相同种子会直接返回上次产物（实测 15 秒"跑完"）。
测性能或要新画面时**必须换 seed**，`driver/bench.py` 已加 `--seed` 参数。

## 修订后的产能

| 用途 | 步数 | 单条 10 秒竖屏 |
|---|---|---|
| 草稿迭代（8 步 turbo） | 8 | **~4.7 分钟** |
| 精修（20 步） | 20 | ~10 分钟（外推） |
| 精修（25 步） | 25 | ~12.5 分钟（外推） |

草稿阶段 **一小时约 12 条 10 秒镜头**（提速前是 6 条）。
20/25 步为线性外推，未实测。

冷启动（ComfyUI 刚重启）额外约 280 秒加载 46 GB 权重，**服务不要频繁重启**。
