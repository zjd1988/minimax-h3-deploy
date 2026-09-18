"""MiniMax-H3 工作流构建器（API 格式）。

三种镜头类型统一在这里生成：
  t2v  —— 纯文生视频（FL2VA DiT + 8step turbo）
  r2v  —— 参考图驱动，保角色一致性（Ref2VA DiT + 4step turbo）
  cont —— r2v 基础上用 AddGuide 锚定上一镜头尾帧，做无缝衔接

节点 id 沿用官方模板的编号，方便和 workflows/*.json 对照。
"""

MODELS = {
    "dit_fl2va":  "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "dit_ref2va": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "clip":       "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "vae_video":  "minimax_h3_video_vae_fp16.safetensors",
    "vae_audio":  "minimax_h3_audio_vae_fp32.safetensors",
    "lora_fl2v_8step": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    "lora_ref2v_4step": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
}

DEFAULT_STEPS = {"t2v": 8, "r2v": 4, "cont": 4}


def frames_for(seconds):
    """时长→帧数。对齐到 17k+5 网格（官方模板的 ComfyMathExpression）。"""
    f = max(5, round(seconds * 24))
    return f + (5 - (f % 17))


def _common(aspect, megapixels, dit, lora, steps, seed, prefix):
    return {
      "115": {"class_type": "ResolutionSelector", "inputs": {
                "aspect_ratio": aspect, "megapixels": megapixels, "multiple": 32}},
      "119": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae_video"]}},
      "120": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae_audio"]}},
      "127": {"class_type": "UNETLoader", "inputs": {
                "unet_name": dit, "weight_dtype": "default"}},
      "128": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": MODELS["clip"], "type": "minimax"}},
      "145": {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": ["127", 0], "lora_name": lora, "strength_model": 1.0}},
      "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
      "124": {"class_type": "BasicScheduler", "inputs": {
                "model": ["145", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
      "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
      "122": {"class_type": "VAEDecode", "inputs": {"samples": ["125", 0], "vae": ["119", 0]}},
      "121": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["125", 0], "vae": ["120", 0]}},
      "130": {"class_type": "CreateVideo", "inputs": {
                "images": ["122", 0], "fps": 24.0, "audio": ["121", 0]}},
      "92":  {"class_type": "SaveVideo", "inputs": {
                "video": ["130", 0], "filename_prefix": prefix,
                "format": "auto", "codec": "auto"}},
    }


def _attach_refs(wf, node_id, ref_images):
    """AUTOGROW 输入：键名形如 ref_images.ref_image_0，最多 9 张。"""
    for i, fn in enumerate(ref_images[:9]):
        nid = str(900 + i)
        wf[nid] = {"class_type": "LoadImage", "inputs": {"image": fn}}
        wf[node_id]["inputs"]["ref_images.ref_image_%d" % i] = [nid, 0]


def build(kind, prompt, seconds=10.0, megapixels=0.98,
          aspect="9:16 (Portrait Widescreen)", steps=None, seed=1,
          ref_images=None, ref_image_size="max",
          prev_video=None, prev_frames=None, guide_frames=22, guide_audio=True,
          prefix="video/out"):
    if kind not in ("t2v", "r2v", "cont"):
        raise ValueError("kind 必须是 t2v / r2v / cont，收到 %r" % kind)
    steps = DEFAULT_STEPS[kind] if steps is None else steps
    length = frames_for(seconds)
    ref_images = ref_images or []

    if kind == "t2v":
        wf = _common(aspect, megapixels, MODELS["dit_fl2va"],
                     MODELS["lora_fl2v_8step"], steps, seed, prefix)
        wf["131"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["128", 0], "vae": ["119", 0], "prompt": prompt,
            "width": ["115", 0], "height": ["115", 1], "length": length}}
        cond_src, latent_src = ["131", 0], ["131", 1]
    else:
        if not ref_images:
            raise ValueError("%s 需要至少一张参考图" % kind)
        wf = _common(aspect, megapixels, MODELS["dit_ref2va"],
                     MODELS["lora_ref2v_4step"], steps, seed, prefix)
        wf["136"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["128", 0], "vae": ["119", 0], "audio_vae": ["120", 0],
            "prompt": prompt, "width": ["115", 0], "height": ["115", 1],
            "length": length, "ref_image_size": ref_image_size}}
        _attach_refs(wf, "136", ref_images)
        cond_src, latent_src = ["136", 0], ["136", 1]

        if kind == "cont":
            if not prev_video:
                raise ValueError("cont 需要 prev_video")
            if prev_frames is None:
                raise ValueError("cont 需要 prev_frames（上一镜头总帧数）")
            start = max(0, prev_frames - guide_frames)
            wf["200"] = {"class_type": "LoadVideo", "inputs": {"file": prev_video}}
            wf["201"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["200", 0]}}
            wf["202"] = {"class_type": "GetImageRangeFromBatch", "inputs": {
                "images": ["201", 0], "start_index": start, "num_frames": guide_frames}}
            # 注意：AddGuide 只输出 CONDITIONING，latent 仍走 136 的输出 1
            wf["203"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
                "positive": ["136", 0], "latent": ["136", 1], "frame_idx": 0,
                "vae": ["119", 0], "audio_vae": ["120", 0], "image": ["202", 0]}}
            if guide_audio:
                wf["203"]["inputs"]["audio"] = ["201", 1]
            cond_src = ["203", 0]

    wf["126"] = {"class_type": "BasicGuider", "inputs": {
        "model": ["145", 0], "conditioning": cond_src}}
    wf["125"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["129", 0], "guider": ["126", 0], "sampler": ["123", 0],
        "sigmas": ["124", 0], "latent_image": latent_src}}
    return wf, length
