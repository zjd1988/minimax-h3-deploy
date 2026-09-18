# P4 编排层

日期：2026-09-02

## 做了什么

把之前三个散落的脚本（`bench.py` / `bench_r2v.py` / `bench_cont.py`）统一成：

```
driver/wf.py         工作流构建器（t2v / r2v / cont 三种镜头统一在这里生成）
driver/pipeline.py   编排器：队列 → 提交 → 幂等 → 衔接 → 拼接
scripts/svc.sh       服务管理（start/stop/restart/status）
jobs/<id>.json       一条片子的定义
jobs/<id>.manifest.json  运行状态（自动生成，幂等恢复的依据）
```

## job 格式

```json
{
  "id": "fox_ep01",
  "refs": ["fox_sheet.png"],
  "concat": true,
  "defaults": {"seconds": 10, "megapixels": 0.98,
               "aspect": "9:16 (Portrait Widescreen)",
               "ref_size": "max", "guide_frames": 22, "guide_audio": true},
  "shots": [
    {"name": "s01", "seed": 1001, "prompt": "..."},
    {"name": "s02", "seed": 1002, "prompt": "Continuing directly from the previous shot, ..."}
  ]
}
```

第一个镜头自动用 `r2v`（参考图保角色），后续自动用 `cont`（AddGuide 接上一镜头）。
单个镜头可用 `"kind"` 覆盖，也可覆盖 `defaults` 里的任何字段。

## 幂等：为什么重要，怎么做的

一个 10 秒镜头要烧 3.4 分钟 GPU。跑到第 5 个镜头崩了，如果从头重来就是纯浪费。

核心做法：**`POST /prompt` 拿到 `prompt_id` 后立刻写 manifest**，然后才开始轮询。
重跑同一个 job 时：

- 已有 `output` 且文件在 → 直接跳过
- 有 `prompt_id` 但没 `output` → 只查 `/history/<id>`，**绝不重新提交**
- 都没有 → 才提交

manifest 用 `os.replace()` 原子写入，避免崩在半截留下坏文件。

**实测**：4 镜头 job 跑完后重跑，**0.23 秒全部跳过，零 GPU 消耗**。

## 用法

```bash
cd /root/video-pipeline

bash scripts/svc.sh start            # 起 ComfyUI + pipeline watch
bash scripts/svc.sh status           # 看状态
bash scripts/svc.sh stop

# 跑单个 job
/root/miniconda3/bin/python driver/pipeline.py --job jobs/fox_ep01.json
# 只校验不生成（不烧 GPU）
/root/miniconda3/bin/python driver/pipeline.py --job jobs/fox_ep01.json --dry-run
# 常驻，扔 json 进 jobs/ 就自动跑
/root/miniconda3/bin/python driver/pipeline.py --watch
```

## ⚠️ 本机没有 systemd

PID 1 是平台的 supervisord，且 `supervisord.conf` **没有 `[include]` 段**——
改它有搞挂 sshd / code-server 的风险，平台升级也可能覆盖。
所以服务管理用 `scripts/svc.sh`（nohup + pidfile）。
`scripts/comfyui.service` 和 `scripts/vidpipe.service` 保留着，
是将来迁到真实 VM 时的参考，**在本机无效**。

## 实测：4 镜头全自动

| 镜头 | 类型 | 耗时 |
|---|---|---|
| s01 | r2v | 2.9 分钟 |
| s02 | cont | 3.5 分钟 |
| s03 | cont | 3.5 分钟 |
| s04 | cont | 3.5 分钟 |
| **合计** | | **13.3 分钟 → 40.5 秒成片** |

产物：`releases/fox_ep01.mp4`，768×1344 / 40.5s / H.264 + AAC。

**产能：约 3 分钟 GPU 时间产出 10 秒成片；一条 60 秒片子约 20 分钟。**

## 累积漂移：识别稳，但构图和色调会漂

跨 4 个镜头检查（各取第 5 秒）：

**稳的**：角色身份完全没塌——橙毛白胸、深褐耳尖、粗眉、吻部雀斑、尾巴白尖，四个镜头一致。

**漂的**：
1. **构图/景别漂得厉害** —— s01 中远景、s02 大特写、s03 中景、s04 全身远景。
   AddGuide 只锚开头几帧，镜头一长就跑了。
2. **色温漂移** —— s01 冷蓝 → s02/s03 偏绿 → s04 暖金。
3. **线条粗细变化** —— s02 的描边明显比 s01 粗。
4. **s01 没按提示词来** —— 提示词写的是"坐在水边"，实际狐狸在水里。

**结论：不能指望衔接自动维持构图和画风，每个镜头的提示词都要显式重申景别、色调、线条风格。**
建议在 job 的 `defaults` 里加一段固定的风格前缀，拼进每个镜头的 prompt。

## 尚未做

- ~~风格前缀自动拼接~~ → 已补，见下方「P4 补充」
- ~~失败重试策略~~ → 已补
- ~~镜头级别的重跑~~ → 已补
- `--watch` 的并发控制（现在串行，够用，因为 GPU 只有一块）

---

# P4 补充（2026-09-02）

针对上面「尚未做」里的三条，已全部补上。

## 1. 风格前缀自动拼接 —— 治漂移

job 里加 `style`（前缀）和 `style_suffix`（后缀），会自动拼进**每一条**镜头提示词：

```json
{
  "style": "Hand-drawn 2D animation, clean uniform medium-weight black outlines, flat cel shading, consistent cool moonlit blue and teal palette throughout. The same cartoon fox: orange fur, white chest and muzzle, dark brown ear tips and paws, thick dark eyebrows, freckled snout, white-tipped tail.",
  "style_suffix": "Medium shot, the fox is fully visible and centered in frame from the very first frame. Do not change the art style, line weight, or color temperature.",
  "shots": [{"name": "s01", "prompt": "只写这个镜头发生了什么"}]
}
```

最终 prompt = `style` + 镜头 prompt + `style_suffix`。
单个镜头可用同名字段覆盖；设成 `""` 则该镜头不加。

设计依据：实测跨镜头会漂**景别、色温、线条粗细**（见上文），
AddGuide 只锚开头几帧管不住。把这三样固定写进每条 prompt 是最省事的治法。
前缀负责画风+角色特征，后缀负责构图+"不要改变风格"的显式约束。

## 2. 失败重试

`--retries N`（默认 2，即最多 3 次尝试）。单个镜头失败后自动重试，退避 20s / 40s。

关键细节：**失败后要把 manifest 里的 `prompt_id` 删掉**。
否则下次重跑会命中"已提交过，只查状态"的幂等分支，永远卡在失败状态上。
manifest 里保留 `attempts` 计数和 `last_error` 便于排查。

提交本身失败（ComfyUI 挂了、网络断了）也会重试，退避 30s / 60s。

## 3. 镜头级重跑

```bash
--redo s02                 # 重做 s02 及其下游（默认级联）
--redo s02 --no-cascade    # 只重做 s02
--redo all                 # 整条重做
```

**默认级联是有原因的**：s03/s04 是用 AddGuide 从**旧的** s02 接出来的。
只重做 s02 而不动下游，成片的衔接就对不上了。
`--no-cascade` 留给你明确知道自己在干什么的场合。

失效时会同时清掉 manifest 里的 `release`，强制重新拼接。
镜头名写错会直接报错并列出可用名字，不会静默跑错。

## 实测

```
--redo s03            → 失效 s03, s04，保留 s01, s02        ✅
--redo s03 --no-cascade → 只失效 s03，保留 s01, s02, s04     ✅
--redo s99            → 报错 "未知镜头名 ['s99']，可用：s01..s04"  ✅
```

## 参考示例

`jobs/fox_ep02.json` 是带完整 `style` / `style_suffix` 的模板，照着改就行。

## 风格前缀的实测效果：部分有效，别当银弹

同一角色、同样的两个镜头，A/B 对比（各取第 5 秒）：
`fox_ep01`（无前缀）vs `fox_ep02`（有 `style` + `style_suffix`）。

**修好了的：**

1. **首镜头构图** —— ep01 的 s01 狐狸泡在水里（提示词写的是"坐在水边"）、景别怪；
   ep02 的 s01 狐狸完整居中、端坐在苔藓石上，完全符合提示词。
   这条归功于 `style_suffix` 里的 "fully visible and centered in frame from the very first frame"。
2. **色温** —— ep02 两个镜头都稳在冷蓝/青绿；ep01 的 s02 明显偏绿偏暖。
3. **线条粗细** —— ep02 两镜头描边明显更一致。

**没修好的：**

- **衔接镜头的景别照样漂。** 尽管 `style_suffix` 明写 "Medium shot, fully visible and centered"，
  ep02 的 s02 仍然变成了大特写、狐狸被裁切。

原因推测：`cont` 镜头里 AddGuide 把上一镜头尾帧锚在第 0 帧，
**图像锚定的权重压过了文字构图指令**。上一镜头结尾接近特写，下一镜头就从特写开始。

**实用建议：**

- 风格前缀对**画风、色温、线条、首镜头构图**有效，值得每个 job 都写上
- **衔接镜头的景别控制不了**，两条路：
  1. 分镜时就接受"景别由上一镜头结尾决定"，顺着它写下一镜头的动作
  2. 需要强制切景别时，别用 `cont`，把该镜头设成 `"kind": "r2v"` 重新起一个镜头
     （代价是丢掉无缝衔接，但成片里用硬切反而更像正常剪辑）
- 减小 `guide_frames`（默认 22）可能削弱图像锚定、让文字指令占更多权重，**未实测**
