# video-pipeline

**动画自媒体视频生产管线** —— 基于 MiniMax-H3（视频+音频一体生成）+ ComfyUI。
原跑在 RTX 4090 D 24GB,已在本仓库于 **2× RTX 3090(24GB)完整复现**:
样例成片 `releases/owl_ep01.mp4`(60s 竖屏,音画一体)。

> 从零复现见 **[docs/REPRO_GUIDE.md](docs/REPRO_GUIDE.md)**(步骤+十大踩坑点),
> 单机适配细节见 [docs/LOCAL_REBUILD.md](docs/LOCAL_REBUILD.md)。

一条命令出一条 60 秒竖屏动画：角色一致、镜头衔接、自带配乐音效，
768×1344 直出，发抖音/小红书不用裁切。

**状态：已跑通，可日常使用。** 4090 D 实测 ≈ 21 分钟出一条 60 秒成片;
3090(novram 模式)约 131 分钟,提速方向见 REPRO_GUIDE.md。

---

## 快速开始

```bash
ssh caoyang_lsem_dev01 && cd /root/video-pipeline

bash scripts/svc.sh status                                    # 看服务
bash scripts/svc.sh start                                     # 起服务

# 1. 造角色（每个角色一次，约 4 分钟）
python driver/make_character.py --name owl --frames 3 \
  --desc "a small round baby owl with huge amber eyes, ..."

# 2. 写分镜 → jobs/owl_ep01.json（照抄现有的改）

# 3. 跑
python driver/pipeline.py --job jobs/owl_ep01.json --dry-run  # 先空跑校验
python driver/pipeline.py --job jobs/owl_ep01.json            # 正式跑

# 4. 不满意就重做某个镜头（默认级联重做下游）
python driver/pipeline.py --job jobs/owl_ep01.json --redo s03
```

成片在 `releases/<id>.mp4`。

想看 ComfyUI 界面，在 **Mac 上**开隧道：
`ssh -N -L 8188:127.0.0.1:8188 caoyang_lsem_dev01` → `http://localhost:8188`

---

## 文档

| 文档 | 什么时候看 |
|---|---|
| **[docs/PRODUCTION.md](docs/PRODUCTION.md)** | **日常创作**：造角色 → 写分镜 → 跑 → 改，含写提示词的四条经验 |
| **[docs/OPERATIONS.md](docs/OPERATIONS.md)** | **日常运维**：启停、目录约定、排错、中断恢复 |
| [docs/STACK.md](docs/STACK.md) | 技术栈：每层用了什么、为什么、版本、来源 |
| [docs/CAPACITY.md](docs/CAPACITY.md) | 产能：实测耗时、日产能、成本模型、还能怎么提速 |
| **[docs/BUILDLOG.md](docs/BUILDLOG.md)** | **搭建全记录：21 个坑、经验、教训**。接手的人先读这份 |
| [docs/LICENSING.md](docs/LICENSING.md) | 商用许可（附 `legal/` 原文） |
| [docs/BENCHMARK.md](docs/BENCHMARK.md) | P3 基准数据 |
| [docs/SAGEATTENTION.md](docs/SAGEATTENTION.md) | SageAttention 编译与提速 |
| [docs/REF2VA.md](docs/REF2VA.md) | 参考图驱动 / 角色一致性 |
| [docs/ADDGUIDE.md](docs/ADDGUIDE.md) | 镜头衔接 |
| [docs/PIPELINE.md](docs/PIPELINE.md) | 编排层设计 |

---

## ⚠️ 三条必读约束

### 1. 必须设 `LD_LIBRARY_PATH` 指向 CUDA 前向兼容层

内核驱动是 535.154.05，但镜像里有 CUDA 13.0 的前向兼容库。不设这个变量，
torch 会加载真 535 驱动并报 `driver too old (found version 12020)`，CUDA 不可用。

```bash
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat:$LD_LIBRARY_PATH
```

`scripts/start_comfyui.sh` 已内置。**自己写脚本别忘了。**

### 2. GitHub / pytorch.org / HuggingFace 都不通，一切走国内镜像

ComfyUI 和自定义节点走 `gitcode.com/gh_mirrors/co/...`，
torch cu130 走交大 `pytorch-wheels`，模型走 ModelScope，HF 走 `hf-mirror.com`。
详见 [STACK.md](docs/STACK.md) 的网络约束表。

### 3. ComfyUI 有结果缓存

相同提示词 + 相同种子直接返回旧产物（会出现 15 秒"跑完"的假象）。
**要新画面或测性能，必须换 `seed`。**

---

## 目录

```
driver/     wf.py 工作流构建 / pipeline.py 编排 / make_character.py 角色设定图
scripts/    启动、服务管理、SageAttention 编译、模型下载清单
assets/     角色设定图 + 角色档案
jobs/       <id>.json 分镜定义 + <id>.manifest.json 运行状态
outputs/    按镜头存的素材      releases/  拼好的成片
models/     75 GB 权重          legal/     许可原文
docs/       文档               logs/      日志
```

---

## 能力与产能

| 能力 | 状态 |
|---|---|
| 文生视频（含音频） | ✅ |
| 参考图驱动，跨镜头角色一致 | ✅ 实测 6 镜头零漂移 |
| 镜头无缝衔接 | ✅ AddGuide 锚定尾部 22 帧 |
| 音画一体（对白/音效/配乐） | ✅ 模型直出 AAC 立体声 |
| 竖屏 768×1344 直出 | ✅ 无需后期裁切 |
| 断点恢复 | ✅ manifest 幂等，重跑 0.23 秒零消耗 |
| 镜头级重做（级联失效下游） | ✅ |

| 环节 | 实测耗时 |
|---|---|
| 造角色（一次性） | 4.1 分钟 |
| 单镜头 10 秒（首镜头 / 衔接） | 2.9 / 3.7 分钟 |
| **一条 60 秒片（6 镜头）** | **≈ 21 分钟** |
| 现实日产能（含写分镜、看片、返工） | 6–10 条 |

详见 [CAPACITY.md](docs/CAPACITY.md)。

---

## ⚖️ 商用

许可挂在**模型权重**上，不在 ComfyUI 上——用什么软件跑都一样。

按 MiniMax H3 Community License（原文在 `legal/`）：

- 本地生成、商业使用**免版税可行**，年收入 < 2000 万美元无需单独授权
- **必须在界面显著标注 "MiniMax H3"** —— 硬性要求
- **不得在美国/欧盟/英国/韩国使用或展示，"Outputs"（生成的视频）本身也算**
  → **本项目不出海，此条不影响**；国内平台在授权范围内
- 国内发布另需按《人工智能生成合成内容标识办法》做 AI 标识（法律义务，与许可无关）

完整解读见 [LICENSING.md](docs/LICENSING.md)。**这是阅读整理，不是法律意见。**

---

## 下一步可做的

- 4 步 turbo LoRA 用于 FL2VA（已下载未测，理论再快一倍）
- 草稿用 0.4 MP 出、定稿再上 0.98 MP（0.4 MP 实测 0.74 秒/步，快得多）
- 引导帧从 22 减到 11，看能否让文字构图指令占更多权重
- 多角色同框一致性
- 参考视频 / 参考音频输入（锁运镜和音色）
- 10 个 embeddings 运镜特效（子弹时间、螺旋上升等）全未测
