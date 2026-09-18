# P5 生产手册 —— 从一个想法到一条成片

前面 P0–P4 解决的是"能不能做"，这份文档解决"怎么反复做"。
全流程四步，除了写提示词都是脚本化的。

---

## 第 0 步：造角色（一次性，每个角色做一次）

```bash
cd /root/video-pipeline
/root/miniconda3/bin/python driver/make_character.py \
  --name owl --frames 3 --seconds 6 \
  --desc "a small round baby owl with huge amber eyes, soft cream-colored chest feathers, warm brown wings with white speckles, two tiny ear tufts, orange beak and feet, wearing a small knitted red scarf"
```

原理：用 T2V 生成一段**角色在纯色背景前转身**的短片，再抽 3 帧当设定图。
提示词骨架写死在脚本里，三个要点：

- `plain flat light grey background, no scenery, no props, no floor` —— 核心。
  实测（REF2VA.md 坑 1）用场景截图当参考，参考场景会被拖进新镜头开头约 2.5 秒。
- `front view, three-quarter view, side view, back` —— 一段片子拿到多个角度
- `static camera` —— 镜头不动，抽帧才干净

耗时约 4 分钟。产物：`assets/<name>_sheet_{0,1,2}.png`（已自动复制进 `ComfyUI/input/`）
和 `assets/<name>.json`（记着描述和产物清单）。

**验收**：打开设定图看背景是否干净、角色特征是否齐全。不满意就换 `--seed` 重跑，
比后面发现角色不对再返工便宜得多。

---

## 第 1 步：写分镜（唯一需要动脑的一步）

在 `jobs/<id>.json` 里写。结构：

```json
{
  "id": "owl_ep01",
  "refs": ["owl_sheet_0.png", "owl_sheet_1.png", "owl_sheet_2.png"],
  "concat": true,
  "style": "画风 + 调色 + 角色特征（会拼进每一条 prompt 的开头）",
  "style_suffix": "构图约束 + 不要改变风格（拼进每一条的结尾）",
  "defaults": { "seconds": 10, "megapixels": 0.98,
                "aspect": "9:16 (Portrait Widescreen)",
                "ref_size": "max", "guide_frames": 22, "guide_audio": true },
  "shots": [
    { "name": "s01", "seed": 3001, "prompt": "这个镜头发生了什么" },
    { "name": "s02", "seed": 3002, "prompt": "Continuing directly from the previous shot. ..." }
  ]
}
```

**写提示词的四条经验（都是踩出来的）：**

1. **画风、调色、角色特征写进 `style`，不要写进每条 prompt。**
   跨镜头会漂色温和线条粗细，固定前缀是最省事的治法（PIPELINE.md 有 A/B 实测）。
2. **第一个镜头必须写构图**，`medium shot, fully visible and centered in frame
   from the very first frame`。设定图只给身份线索、不给空间线索，
   不写构图的话角色可能前几秒不在画面里（REF2VA.md 坑 2）。
3. **衔接镜头开头写 `Continuing directly from the previous shot.`**
4. **每条 prompt 都要写音频**（对白/音效/音乐）。H3 是音画一体生成，
   不写音频等于浪费掉它相对其他模型最大的优势。

**分镜长度**：单镜头 5–10 秒。注意力随帧数平方增长，长镜头成本涨得很快
（BENCHMARK.md：计算量 15× 对应耗时 85×）。

**景别的现实**：衔接镜头的景别由上一镜头结尾决定，文字压不住（PIPELINE.md A/B 实测）。
两条路——顺着它写下一镜头的动作；或者需要强制切景别时把该镜头设成 `"kind": "r2v"`，
放弃无缝衔接换硬切（成片里硬切反而更像正常剪辑）。

---

## 第 2 步：跑

```bash
# 先空跑校验，不烧 GPU
/root/miniconda3/bin/python driver/pipeline.py --job jobs/owl_ep01.json --dry-run
# 正式跑
/root/miniconda3/bin/python driver/pipeline.py --job jobs/owl_ep01.json
```

或者起常驻服务，往 `jobs/` 里扔 json 就自动跑：

```bash
bash scripts/svc.sh start     # ComfyUI + pipeline watch
bash scripts/svc.sh status
```

跑的过程：第一个镜头用 Ref2VA（参考图保角色），后续自动用 AddGuide 接上一镜头，
全部完成后 ffmpeg 拼成 `releases/<id>.mp4`。中断了直接重跑，
已完成的镜头会跳过（manifest 幂等，实测重跑 0.23 秒零 GPU 消耗）。

---

## 第 3 步：改

看成片，哪个镜头不满意就重做那个：

```bash
# 重做 s03 及其下游（默认级联——下游是从旧 s03 接出来的）
/root/miniconda3/bin/python driver/pipeline.py --job jobs/owl_ep01.json --redo s03
# 只重做 s03，不动下游（衔接可能对不上，你确定就行）
... --redo s03 --no-cascade
```

改提示词后重跑同一条命令即可。换 `seed` 可以在提示词不变的情况下换一版画面
（**必须换 seed**，ComfyUI 有结果缓存，同提示词同种子会直接返回旧产物）。

---

## 时间与产能

| 环节 | 耗时 |
|---|---|
| 造角色（一次性） | ~4 分钟 |
| 单个 10 秒镜头（首镜头 r2v） | ~2.9 分钟 |
| 单个 10 秒镜头（衔接 cont） | ~3.5 分钟 |
| **一条 60 秒片子（6 镜头）** | **~21 分钟** |

按每天有效 8 小时算，理论上限约 20 条 60 秒成片/天，
实际要扣掉写分镜、看片、返工重做的时间。

---

## 目录约定

```
assets/      角色设定图 + <name>.json（角色档案）
jobs/        <id>.json 分镜定义 / <id>.manifest.json 运行状态（自动生成）
outputs/     <job_id>/ 下按镜头存的素材
releases/    <id>.mp4 拼好的成片
logs/        comfyui.log / pipeline_<id>.log
```

---

## ⚖️ 商用许可 → 详见 LICENSING.md

已核对许可原文（`../legal/MiniMax-H3-Community-License.txt`）。三句话版本：

1. 本地生成、商业使用 **免版税可行**（年收入 < 2000 万美元无需单独授权）
2. **必须在界面显著标注 "MiniMax H3"** —— 这是硬性要求
3. **不得在美国/欧盟/英国/韩国使用或展示，"Outputs" 即生成的视频本身也算**
   → 国内平台没问题；YouTube / TikTok 国际版 / Instagram 会踩线
