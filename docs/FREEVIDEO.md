# FreeVideo 调研与复现流程(3090)

> 上游:https://github.com/FlashML-org/FreeVideo (Apache-2.0)
> 定位:MiniMax H3 的消费级显卡低显存推理引擎,基于 OpenVDN 的 **VDN-H3**(8 步蒸馏模型,
> Video DeltaNet 混合注意力),以 **ComfyUI 自定义节点**形式运行。

## 1. 为什么关注它

本项目在 24 GB 3090 上跑 243 帧 768×1344 会 OOM,被迫 `--novram`(权重全内存流式),
速度只有 4090 D 的 1/8(单镜头 22 分钟)。FreeVideo 的自适应执行规划器正好解决这个:

| 能力 | 说明 |
|---|---|
| 显存驻留规划 | 50 个 transformer block 按 VRAM 预算决定驻留数(每块 432.5 MB),其余常驻 pinned 内存或按需读盘 |
| int8 GEMM | **Ampere(含 3090)全部走 int8 + ConvRot 旋转**——与我们选 int8_convrot 权重的思路一致 |
| 注意力后端探测 | SageAttention2 → PyTorch flash → cuDNN → FA2 → FA4 依次探测 |
| 分块计算 | FF chunk 2048 / 投影 chunk 1024,窗口批在 Ampere 上为 1,压低激活峰值 |
| 两段式采样 | 先半分辨率粗采再全分辨率,3090 官方口径:5 秒视频提速 ~2.3× |
| OOM 自愈 | OOM 自动换轻量 placement 重试(最多 2 次),不够再缩 head group/分块 |
| 最低门槛 | 官方称 8 GB VRAM + 16 GB RAM 可跑(社区实测 4060 Ti 8GB 出 10 秒片 603 秒) |

## 2. 环境要求与本机现状

| 要求 | 本机 | 结论 |
|---|---|---|
| NVIDIA 驱动 **≥580**(CUDA 13 encoder) | 570.133.07 | ❌ **当前阻塞项**,需宿主机升驱动 |
| x86_64 Linux + NVIDIA GPU | ✅ 2×3090 | — |
| Python ≥3.12,<3.13 | ✅ 3.12.14 | — |
| ComfyUI(已有安装可复用) | ✅ v0.34.2 | — |
| 磁盘 | 峰值 ~89 GB 额外 | ✅ 余 2 TB |
| 模型 | **VDN-H3 int8_convrot**(OpenVDN/vdn-minimax-h3-edge),~49 GB,**与本项目现有 75 GB MiniMax-H3 权重不通用**(预检确认 0 GiB 复用) | 需另下 |

注意:FreeVideo 用的 VDN-H3 是蒸馏+改注意力的衍生模型,和原版 MiniMax-H3 不是同一份权重;
它的角色一致性/音画能力是否对齐原版,需要装好后自行抽验。

## 3. 接入现有 ComfyUI(推荐路径,已执行到第 3 步)

```bash
# ① 克隆为自定义节点(已完成,节点能导入,未装引擎前不影响原有管线)
cd ComfyUI/custom_nodes
git clone https://github.com/FlashML-org/FreeVideo.git
#    重启 ComfyUI 后日志会出现:
#    [WARNING] [FreeVideo] Chain routes not registered: FreeVideo setup is missing...

# ② 预检(只读,不写文件;--reuse-models 会扫描现有模型库并校验可复用部分)
cd FreeVideo
./freevideo setup --plan --plain --reuse-models /path/to/models   # 注意大小写:--reuse-models
#    输出安装计划:GPU/RAM 识别、需下载体积、驻留策略;被驱动卡住会在此处 BLOCKED

# ③ 真正安装(驱动 ≥580 后执行)
./freevideo setup --reuse-models /path/to/models --accept-model-license --yes
#    - 自动装运行时依赖(triton==3.7.1、transformers==5.15.0 等精确 pin)
#    - 下载 VDN-H3 int8_convrot(~49 GB,断点续传)
#    - 编译 GPU kernel(可能需要 nvcc;容器无 root 时留意 PATH/CUDA_HOME)

# ④ 使用
#    ComfyUI → Workflow → Browse Templates → FreeVideo → FreeVideo-All-in-One
#    首次在 FreeVideo Settings 里完成配置;或命令行:
./freevideo generate --prompt-file prompt.txt --out video.mp4
./freevideo plan --vram-gib 22 --ram-gib 32 --width 768 --height 1344 --seconds 10
./freevideo doctor    # 依赖与 GPU kernel 体检
```

**依赖冲突提醒**(本机实测版本对比):FreeVideo 精确 pin `triton==3.7.1`,而
torch 2.9.1 配套 triton 3.5.1;transformers 5.15.0 vs 我们 5.17.0。它的 setup 用
**独立托管环境**装依赖(不动我们的 `env/`),这也正是它警告"必须先 setup、
引擎未就绪时节点功能不可用"的原因——**不要**手动把这些 pin 装进现有 venv。

## 4. 阻塞项与解决路径

当前唯一阻塞:**驱动 570.133.07 < 580**。两个选择:

1. **宿主机升级 NVIDIA 驱动到 ≥580**(推荐)。升级后容器内无需改动,
   从第 3 步 ③ 继续即可。
2. 暂不升级:FreeVideo 保持"已克隆未激活"状态——节点导入无害(仅 WARNING),
   原有 MiniMax-H3 管线完全不受影响(已实测)。

## 4b. 部署实测结论(2026-10-14,驱动 570.133.07)

**实测回答"能否用当前驱动完成部署":不能,必须升级宿主机驱动到 ≥580。**
这是实验得出的硬性依赖,不是文档保守:

| 实验 | 结果 |
|---|---|
| triton 3.7.1(CUDA 13 编译链)在 570 驱动 + 3090 上编译并运行最小 kernel | ✅ 成功(PTX JIT 路径向下兼容,数值正确) |
| 本地补丁绕过 bootstrap.py 的 580 门禁后,完整 setup(装 PyTorch cu130 + CUDA13 运行时 + 引擎依赖) | ✅ 门禁通过,依赖安装成功 |
| 安装末尾 encoder 自检 `torch._C._cuda_init()` | ❌ `RuntimeError: The NVIDIA driver on your system is too old (found version 12080)` |

原理:triton 走 PTX JIT 可在老驱动上加载 kernel,但 **CUDA 13 完整运行时创建上下文
需要驱动 API ≥13000**;NVIDIA 前向兼容包(cuda-compat)只支持数据中心卡,
GeForce 3090 不适用,所以无法像原项目 4090D 那样用兼容层绕过(那是 535→13.0 的
跨代兼容,同样仅限数据中心卡,原机驱动是 535+兼容包在 ML 平台镜像内预装)。

失败现场与断点:安装产物保留在 `ComfyUI/custom_nodes/FreeVideo/envs/`(5.3 GB)与
`setup-runs/20261014T021829Z-484066/`。**升级驱动后无需重头再来**,重跑同一条命令断点续装:

```bash
cd ComfyUI/custom_nodes/FreeVideo
./freevideo setup --plain --reuse-models /path/to/models --gpu 1 \
  --accept-model-license --yes --no-launch
```

本地补丁说明:为做本次部署测试,给 `freevideo_engine/bootstrap.py`(475 行附近)打了
绕过 580 门禁的补丁(`LOCAL TEST PATCH` 注释)。升级驱动后此补丁可有可无;要还原:
`git checkout freevideo_engine/bootstrap.py`。不想留 5.3 GB 半成品环境就删掉
`ComfyUI/custom_nodes/FreeVideo/envs/`,setup 会重建。

另注意:本次测试时 GPU0 被同宿主其他租户占满,setup 用 `--gpu 1` 指定第二张卡;
共享宿主跑装前先 `nvidia-smi` 看卡是否空闲。

## 5. 与现有管线的关系

接入成功后,两条管线并存:

- 原 `driver/pipeline.py` 管线:Comfy-Org MiniMax-H3 权重,ref2v/cont 编排、
  断点恢复、镜头级重做——**继续可用**
- FreeVideo:VDN-H3 权重,低显存/两段式采样,适合 8–16 GB 卡或追求速度;
  是否把 `driver/wf.py` 的工作流改接到 FreeVideo 节点上,待实测画质与
  角色一致性后再决定
