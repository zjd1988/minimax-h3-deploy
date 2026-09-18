# 商用许可 —— 读了原文之后的更正

**我不是律师，下面是对许可原文的阅读整理，不是法律意见。真要变现前请自己读一遍
`../legal/MiniMax-H3-Community-License.txt`，金额大的话找律师看。**

---

## 先更正一个说法

项目最初参考的那份文档说：

> 本地生成的内容用于商业用途需要 MiniMax 商用许可，Comfy 是唯一官方渠道；
> Comfy Cloud 上的生成已含商用权。

**这与许可原文不符。** 原文（`MiniMax H3 COMMUNITY LICENSE AGREEMENT`，2026-08-02）：

- **第 II 条**授予的是 "non-exclusive, non-transferable, **royalty-free**, limited license
  to use, reproduce, distribute, create derivative works... and modify"
  —— 免版税，没有"商用需另购许可"的一般性要求。
- **第 VI.4 条**："**MiniMax claims no rights over the Outputs you generate.**"
  生成的视频，MiniMax 不主张权利。

## 用什么软件跑，与许可无关

ComfyUI 是 GPL-3.0 的开源软件。许可挂在**模型权重**上——
即我们从 ModelScope `Comfy-Org/MiniMax-H3` 下的那 75 GB。
用 ComfyUI、用 diffusers、还是自己写推理代码，在许可上完全一样。

这份许可的出处见 `../legal/SOURCE.md`：ModelScope 那个仓库的 model card 里
`license_link` 直接指向它，就是管着我们这份权重的那一份。

---

## 商用要满足的两条（第 IV 条 Additional Commercial Terms）

**1. 年收入超过 2000 万美元才需要单独书面授权。**
   联系 api@minimax.io，主题写 "MiniMax H3 licensing - authorization request"。
   起步阶段的自媒体号显然够不到这条。

**2. 必须在商业产品/服务的界面上显著展示 "MiniMax H3"。**
   原文："You shall **prominently display** 'MiniMax H3' on the user interface of
   commercial product or service that uses MiniMax H3 or MiniMax H3 Works."

   第 VI.2 条为此专门授予了 "MiniMax H3" 商标的使用许可（仅限用于满足披露义务）。

   这条**是硬性要求**（shall），不是建议。对自媒体号意味着：接广告、带货、
   拿平台分成的时候，得在某个用户看得到的地方标出用了 MiniMax H3。
   具体标在简介、片尾还是视频描述里，许可没细说，需要自行判断或问 MiniMax。

---

## ⚠️ 真正会卡住你的不是"商用"，是**地域**

这是整份许可里对做自媒体最要命的一条，也是原参考文档完全没提的。

- **第 I.3 / I.5 条**：Applicable Territory = 全球，**但排除欧盟、英国、韩国、美国**。
- **第 V.4 条**："You may not use, reproduce, modify, distribute, or **display the
  MiniMax H3 Works or any of their Outputs or results outside the Applicable Territory.**"
- **Exhibit A 第 1 条**把 "Use outside the Applicable Territory" 直接列为禁止用途。

注意 V.4 管的是 **Outputs**，也就是**你生成的视频本身**，不只是模型权重。

**实际影响：**

| 发布渠道 | 情况 |
|---|---|
| 抖音 / 小红书 / B站 / 视频号（面向国内） | 在许可范围内 |
| YouTube / TikTok 国际版 / Instagram | 观众必然含美国、欧盟、英国、韩国 —— **踩到 V.4** |

如果你打算做出海号，或者国内号但走国际分发，这条必须先解决。
第 II 条末尾写了：Excluded Territories 的部署可以联系 MiniMax 单独申请许可。

---

## 其他值得注意的

- **第 V.3 条**：不能用 Outputs 去训练/改进别的 AI 模型。
- **第 III.3.b 条**："encouraged to" 给 AI 生成内容加标识 —— 许可里是**鼓励**不是强制。
  但**中国法规另有要求**（《人工智能生成合成内容标识办法》），
  国内发布该标还得标，那是法律义务，跟这份许可无关。
- **第 VI.3 条**：如果你起诉 MiniMax 侵权，许可自动终止。
- **第 IX 条**：适用香港法，香港法院专属管辖。
- **文本编码器** Qwen3-VL-32B 单独按 Apache 2.0 授权（许可末尾的 Additional Note）。

---

## 小结

| 问题 | 答案 |
|---|---|
| 用 ComfyUI 产出就合规吗？ | **不是。软件无关，许可挂在权重上。** |
| 本地生成能商用吗？ | **能**，免版税，但要满足下面两条 |
| 需要买许可吗？ | 年收入 < 2000 万美元**不需要** |
| 有什么必须做的？ | **界面上显著标注 "MiniMax H3"** |
| 最大的坑是什么？ | **不能在美国/欧盟/英国/韩国使用或展示，包括生成的视频** |
| 国内平台发布？ | 在许可范围内（另需按中国法规做 AI 标识） |
| 出海号？ | **踩线**，需单独联系 MiniMax 申请 |
