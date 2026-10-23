# AGENTS.md — 面向 AI 代理的仓库工作说明

本仓库是 MiniMax H3 动画/演示视频生产管线(ComfyUI + 自研编排层)。
任何 AI 代理(Claude Code / Codex / Cursor 等)在本仓库内**生成视频 prompt 或运行生成任务**
之前,必须遵循本文件。

## 1. 生成视频 prompt 前:必须使用 h3-prompt-writing skill

官方 MiniMax-H3 仓库的提示词技能已收录在本仓库:

```
skills/h3-prompt-writing/
├── SKILL.md                    # 技能入口:工作流与输出规则
└── references/
    ├── base-en.txt             # T2VA / I2VA / FL2VA / L2VA 提示词指南
    └── ref-en.txt              # Ref2VA(多模态参考)六段式改写指南
```

**强制流程**:

1. 判断输入模式:T2VA(纯文本)/ I2VA(首帧)/ FL2VA(首尾帧)/ L2VA(尾帧)/
   Ref2VA(参考图/视频/音频)。
2. base 模式 → 读 `skills/h3-prompt-writing/references/base-en.txt`;
   Ref2VA 模式 → 读 `references/ref-en.txt`。
3. 按指南的**字段名、段落顺序、标签写法**产出 prompt:
   - base 模式三段:`integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`
   - Ref2VA 六段:`subject_definitions` / `summary` / `retention_analysis` /
     `detailed_description` / `overall_soundscape` / `non_diegetic_music`
   - 参考标签(`<Picture 1>`、`<Video 1>`、`<Audio 1>`)全篇保持一致
4. 描述正文用英文;对白、歌词、画面内文字保留原语言(对白用 `<d>[语言]...</d>` 包裹)。
5. 描述总时长必须与请求时长一致(H3 支持 4–15 秒;本管线单镜头 8–10 秒)。
6. 具象细节优先,避免 "cinematic" / "beautiful" 这类空泛词。

> 参考范例:官方仓库 `scripts/readme/full-2k-*.sh` 中的 Context-IR 输出即该结构的标杆。
> 本仓库已生成的样例 prompt 见 `outputs/` 对应任务与 `docs/PRODUCTION.md` 的四条经验。

## 2. 生成任务怎么跑

```bash
# 服务(默认 127.0.0.1:8188,novram 模式)
bash scripts/svc.sh start|status|stop

# 文生视频(t2va)
./env/bin/python driver/bench.py --prompt "<按 skill 产出的 prompt>" \
  --seconds 8 --aspect "16:9 (Widescreen)" --steps 4 --seed <seed>

# 参考图驱动(r2va,角色/场景一致性)
./env/bin/python driver/bench_r2v.py --refs ComfyUI/input/<ref>.png \
  --prompt "<按 skill 产出的 prompt>" --seconds 8 \
  --aspect "16:9 (Widescreen)" --ref-size match --steps 4 --seed <seed>

# 正式生产(分镜 job + 断点恢复 + 自动衔接 + 拼接)
./env/bin/python driver/pipeline.py --job jobs/<id>.json --dry-run   # 先校验
./env/bin/python driver/pipeline.py --job jobs/<id>.json
```

- aspect 可选值见 `ResolutionSelector`:`16:9 (Widescreen)` / `9:16 (Portrait Widescreen)` 等
- 成片输出在 `outputs/video/`,拼好的成片在 `releases/`
- 相同 prompt+seed 会命中 ComfyUI 缓存;要新画面必须换 seed

## 3. 硬约束(勿踩)

1. **显存**:24 GB 卡跑 243 帧 768×1344 必须 `--novram`(已固化进
   `scripts/start_comfyui.sh`);勿手动改回默认模式,会 OOM。
2. **prompt 里的冒号**:`drawtext`/ffmpeg filter 对 `:` 敏感,字幕走
   `textfile=` 或 PNG overlay(参考 `repro/scripts/` 与 releases 生成脚本)。
3. **不要往 `env/` 装其他项目的精确 pin 依赖**(如 FreeVideo 的 triton==3.7.1),
   会破坏现有管线;外部引擎一律用独立环境。
4. **模型文件**:`models/` 75 GB 不入库;下载与校验见 `docs/REPRO_GUIDE.md`。
5. 多人共用宿主时,先 `nvidia-smi` 确认目标 GPU 空闲。

## 4. 文档索引

| 需要什么 | 看 |
|---|---|
| 从零复现 | `docs/REPRO_GUIDE.md` |
| 本机适配记录(3090) | `docs/LOCAL_REBUILD.md` |
| 日常创作(角色/分镜/重做) | `docs/PRODUCTION.md` |
| 编排层设计 | `docs/PIPELINE.md` |
| FreeVideo 低显存引擎 | `docs/FREEVIDEO.md` |
| 原始搭建史与坑 | `docs/BUILDLOG.md` |
