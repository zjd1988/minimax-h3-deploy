"""Ref2VA + AddGuide：保角色一致性 + 接上一镜头的续镜工作流。"""

def build(prompt, ref_images, prev_video, seconds=10.0, megapixels=0.98,
          aspect="9:16 (Portrait Widescreen)", steps=4, seed=1,
          ref_image_size="max", guide_frames=22, prev_total_frames=243,
          with_audio=True, prefix="video/cont"):
    f = max(5, round(seconds * 24))
    length = f + (5 - (f % 17))
    start = max(0, prev_total_frames - guide_frames)

    wf = {
      "115": {"class_type":"ResolutionSelector","inputs":{
                "aspect_ratio":aspect,"megapixels":megapixels,"multiple":32}},
      "119": {"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_video_vae_fp16.safetensors"}},
      "120": {"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_audio_vae_fp32.safetensors"}},
      "127": {"class_type":"UNETLoader","inputs":{
                "unet_name":"minimax_h3_ref2va_pruned_int8_convrot.safetensors","weight_dtype":"default"}},
      "128": {"class_type":"CLIPLoader","inputs":{
                "clip_name":"qwen3vl_32b_minimax_h3_int8_convrot.safetensors","type":"minimax"}},
      "145": {"class_type":"LoraLoaderModelOnly","inputs":{"model":["127",0],
                "lora_name":"minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
                "strength_model":1.0}},
      # --- 上一镜头：载入 → 拆成帧+音频 → 取尾部 N 帧 ---
      "200": {"class_type":"LoadVideo","inputs":{"file":prev_video}},
      "201": {"class_type":"GetVideoComponents","inputs":{"video":["200",0]}},
      "202": {"class_type":"GetImageRangeFromBatch","inputs":{
                "images":["201",0],"start_index":start,"num_frames":guide_frames}},
      # --- 新镜头的条件与 latent ---
      "136": {"class_type":"MiniMaxH3ReferenceToVideo","inputs":{
                "clip":["128",0],"vae":["119",0],"audio_vae":["120",0],
                "prompt":prompt,"width":["115",0],"height":["115",1],
                "length":length,"ref_image_size":ref_image_size}},
      # --- 把上一镜头尾帧锚在第 0 帧 ---
      "203": {"class_type":"MiniMaxH3AddGuide","inputs":{
                "positive":["136",0],"latent":["136",1],"frame_idx":0,
                "vae":["119",0],"audio_vae":["120",0],"image":["202",0]}},
      "123": {"class_type":"KSamplerSelect","inputs":{"sampler_name":"res_multistep"}},
      "124": {"class_type":"BasicScheduler","inputs":{"model":["145",0],
                "scheduler":"simple","steps":steps,"denoise":1.0}},
      "126": {"class_type":"BasicGuider","inputs":{"model":["145",0],"conditioning":["203",0]}},
      "129": {"class_type":"RandomNoise","inputs":{"noise_seed":seed}},
      "125": {"class_type":"SamplerCustomAdvanced","inputs":{"noise":["129",0],
                "guider":["126",0],"sampler":["123",0],"sigmas":["124",0],
                "latent_image":["136",1]}},
      "122": {"class_type":"VAEDecode","inputs":{"samples":["125",0],"vae":["119",0]}},
      "121": {"class_type":"VAEDecodeAudio","inputs":{"samples":["125",0],"vae":["120",0]}},
      "130": {"class_type":"CreateVideo","inputs":{"images":["122",0],"fps":24.0,"audio":["121",0]}},
      "92":  {"class_type":"SaveVideo","inputs":{"video":["130",0],
                "filename_prefix":prefix,"format":"auto","codec":"auto"}},
    }
    if with_audio:
        wf["203"]["inputs"]["audio"] = ["201", 1]
    for i, fn in enumerate(ref_images[:9]):
        nid = str(900 + i)
        wf[nid] = {"class_type":"LoadImage","inputs":{"image":fn}}
        wf["136"]["inputs"]["ref_images.ref_image_%d" % i] = [nid, 0]
    return wf, length
