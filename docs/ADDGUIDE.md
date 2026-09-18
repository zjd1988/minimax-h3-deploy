# AddGuide 镜头衔接测试

日期：2026-09-02　配置：768×1344 / 10.1s / 243 帧 / 4 步 turbo / SageAttention 开启

## 结论：可用，接缝几乎无跳变

用 `MiniMaxH3AddGuide` 把上一镜头**尾部 22 帧 + 音频**锚定在新镜头 `frame_idx=0`，
新镜头开头在**姿势、场景、色调、线条风格**上无缝延续上一镜头，
随后按提示词自然过渡到新动作（狐狸从坐姿起身 → 走向林间）。

已产出第一条多镜头成片：`releases/fox_2shot_20s.mp4`，20.3 秒 / 2 镜头 /
ffmpeg `-c copy` 直接拼接、无转场特效。

## 节点链路

官方的 `video_minimax_h3_i2v_continuation.json` 模板**没有用 AddGuide**
（它用的是"上镜头尾帧当下镜头首帧"的简单做法）。真正的衔接要自己搭：

```
LoadVideo(上一镜头)
  └→ GetVideoComponents  → images(IMAGE批) / audio(AUDIO) / fps
       └→ GetImageRangeFromBatch(start_index=221, num_frames=22)  ← 取尾部22帧
            └→ MiniMaxH3AddGuide(positive, latent, frame_idx=0,
                                 vae, audio_vae, image=尾帧, audio=上镜头音频)
                 └→ BasicGuider  → SamplerCustomAdvanced
```

要点：
- `MiniMaxH3AddGuide` **只输出 CONDITIONING**（`positive`），latent 直通不变。
  采样器的 `latent_image` 仍接 `MiniMaxH3ReferenceToVideo` 的输出 1。
- `frame_idx` 支持负数（从尾部锚定）。
- `image` 接多帧批次时按"片段"锚定，不是单帧。
- 接了 `image` 就必须给 `vae`；接了 `audio` 就必须给 `audio_vae`。

## 速度代价

| 路径 | 秒/步 | 10 秒竖屏总耗时 |
|---|---|---|
| Ref2VA（1 张参考图） | 30.29 | 174 s（2.9 分钟） |
| **Ref2VA + AddGuide（22 引导帧）** | **35.69** | **204 s（3.4 分钟）** |

引导帧带来约 **+18%** 单步开销。多镜头连拍时每镜头约 3.4 分钟。

## 用法

```bash
# 上一镜头先复制进 ComfyUI/input/
cp outputs/video/shot01.mp4 ComfyUI/input/

/root/miniconda3/bin/python driver/bench_cont.py \
  --refs fox_sheet.png \
  --prev-video shot01.mp4 --prev-frames 243 --guide-frames 22 \
  --prompt "Continuing directly from the previous shot, 同角色 + 同色调 + 新动作 + 镜头 + 音频" \
  --seconds 10 --steps 4 --seed 88 --prefix video/shot02
```

提示词里写 "Continuing directly from the previous shot" 并**重申角色、画风、色调**，
配合 AddGuide 效果最好。`--no-audio` 可关掉音频锚定。

## 完整分镜流水线（已验证可跑通）

1. **角色设定图** —— 干净背景，不要用场景截图（见 REF2VA.md 坑 1）
2. **镜头 1**：`bench_r2v.py` + 设定图，提示词写清构图（见 REF2VA.md 坑 2）
3. **镜头 N**：`bench_cont.py` + 设定图 + 上一镜头，锚定尾部 22 帧
4. **拼接**：`ffmpeg -f concat -c copy`，9:16 模型直出无需裁切

单镜头 10 秒约 3.4 分钟，一条 60 秒成片（6 镜头）约 **20 分钟**。

## 尚未测

- 引导帧数量的影响（22 帧是文档建议值，未做 11/33/44 的对比）
- 三镜头以上连续衔接，误差是否累积漂移
- 音频锚定的实际效果（本次开着，但未单独做 A/B 对比）
