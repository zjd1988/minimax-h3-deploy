# P3 基准测试结果

测试日期：2026-09-02　硬件：RTX 4090 D 24GB / 20 vCPU / 78 GB RAM
模型：MiniMax-H3 `fl2va_pruned_int8_convrot` + `qwen3vl_32b_int8_convrot` 编码器
加速：`fl2v_turbo_8step` LoRA，8 步，采样器 `res_multistep` + `simple` 调度

## 实测数据

| 配置 | 分辨率 | 帧数/时长 | 采样速度 | 总耗时 | 产物 |
|---|---|---|---|---|---|
| 冷启动测试 0.4 MP 16:9 | 864×480 | 39 帧 / 1.6s | **0.74 s/步** | **147.6 s** | 135 KB |
| **生产设置 0.98 MP 9:16** | **768×1344** | **243 帧 / 10.1s** | **62.9 s/步** | **557 s (9.3 分钟)** | 2.4 MB |

两条都成功输出 H.264 视频 + **AAC 32kHz 立体声音轨**（音画一体，无需另配音）。
竖屏 768×1344 是模型直出，发抖音/小红书不需要后期裁切。

## 关键结论

**1. int8_convrot 走原生 kernel，方案选型正确。** 日志：

```
Native ops:   float8_e5m2, float8_e4m3fn, asym_w4a8_int8, convrot_w4a4, int8_tensorwise
Emulated ops: mxfp8, nvfp4
```

若按模板默认用 `nvfp4_awq` 编码器会落进 emulated 路径。cu130 + int8_convrot 是这台机器的正解。

**2. 瓶颈是算力，不是显存 offload。** 生产设置下 GPU 利用率稳定 **100%**，显存占用 15.6 GB
（24 GB 上限内）。46 GB 模型（编码器 25.9 + DiT 20.0）靠 ComfyUI 的 dynamic VRAM loading
分批调度，没有成为瓶颈。**这意味着换更小的模型不会有数量级提速**，H3 值得留着用。

**3. 冷启动开销约 140 秒。** 首次生成 147.6 s 里采样只占 5.9 s，其余是加载 46 GB 权重。
模型常驻内存后第二次起省掉这段 —— **ComfyUI 服务不要频繁重启**。

**4. 计算规模换算。** 生产设置比测试设置像素多 2.45×、帧数多 6.2×（合计 ~15×），
实测 62.9 / 0.74 = 85× 慢。超线性是注意力随帧数平方增长导致的，
**这意味着长镜头成本增长很快，分镜应控制在 5–10 秒**。

## 产能估算

| 用途 | 步数 | 单条 10 秒竖屏耗时 |
|---|---|---|
| 草稿迭代（8步 turbo） | 8 | **~9.3 分钟** |
| 精修（20 步，关 turbo） | 20 | **~21 分钟**（外推） |
| 精修（25 步） | 25 | **~26 分钟**（外推） |

按 8 步草稿算，**一小时约 6 条 10 秒镜头**；一条 60 秒成片需 6–12 个镜头，
草稿阶段约 1–2 小时，精修再叠加。20/25 步的数字是按 62.9 s/步线性外推，尚未实测。

## 尚未做的优化

- **SageAttention 未安装**。ComfyUI 有原生节点 `MiniMaxH3MemoryEfficientSageAttentionPatch`，
  官方称可约翻倍速度。GitHub releases 拿不到预编译 wheel，需本地用 nvcc 13.0 编译。
  这是目前**最大的一块待挖性能**。
- 4 步 turbo LoRA（`fl2v_turbo_4step_v1.0_768p`）未测，理论上比 8 步再快一倍。
- 未测 Ref2VA 路径（`ref2va_pruned_int8_convrot` + `ref2v_turbo_4step`），
  那才是动画角色一致性的主力，速度可能与 FL2VA 不同。

## 复现命令

```bash
cd /root/video-pipeline
/root/miniconda3/bin/python driver/bench.py \
  --seconds 10 --megapixels 0.98 --aspect "9:16 (Portrait Widescreen)" \
  --steps 8 --prompt "你的提示词" --prefix video/out
```
