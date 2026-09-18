import json, sys

def build(prompt, seconds=2.0, megapixels=0.4, aspect="16:9 (Widescreen)",
          steps=8, seed=1, prefix="video/bench"):
    # 时长→帧数：模板里的 ComfyMathExpression，对齐到 17k+5 帧网格
    f = max(5, round(seconds * 24))
    length = f + (5 - (f % 17))
    return {
      "115": {"class_type":"ResolutionSelector","inputs":{
                "aspect_ratio":aspect,"megapixels":megapixels,"multiple":32}},
      "119": {"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_video_vae_fp16.safetensors"}},
      "120": {"class_type":"VAELoader","inputs":{"vae_name":"minimax_h3_audio_vae_fp32.safetensors"}},
      "127": {"class_type":"UNETLoader","inputs":{
                "unet_name":"minimax_h3_fl2va_pruned_int8_convrot.safetensors","weight_dtype":"default"}},
      "128": {"class_type":"CLIPLoader","inputs":{
                "clip_name":"qwen3vl_32b_minimax_h3_int8_convrot.safetensors","type":"minimax"}},
      "134": {"class_type":"LoraLoaderModelOnly","inputs":{"model":["127",0],
                "lora_name":"minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
                "strength_model":1.0}},
      "131": {"class_type":"MiniMaxH3ImageToVideo","inputs":{
                "clip":["128",0],"vae":["119",0],"prompt":prompt,
                "width":["115",0],"height":["115",1],"length":length}},
      "123": {"class_type":"KSamplerSelect","inputs":{"sampler_name":"res_multistep"}},
      "124": {"class_type":"BasicScheduler","inputs":{"model":["134",0],
                "scheduler":"simple","steps":steps,"denoise":1.0}},
      "126": {"class_type":"BasicGuider","inputs":{"model":["134",0],"conditioning":["131",0]}},
      "129": {"class_type":"RandomNoise","inputs":{"noise_seed":seed}},
      "125": {"class_type":"SamplerCustomAdvanced","inputs":{"noise":["129",0],
                "guider":["126",0],"sampler":["123",0],"sigmas":["124",0],
                "latent_image":["131",1]}},
      "122": {"class_type":"VAEDecode","inputs":{"samples":["125",0],"vae":["119",0]}},
      "121": {"class_type":"VAEDecodeAudio","inputs":{"samples":["125",0],"vae":["120",0]}},
      "130": {"class_type":"CreateVideo","inputs":{"images":["122",0],"fps":24.0,"audio":["121",0]}},
      "92":  {"class_type":"SaveVideo","inputs":{"video":["130",0],
                "filename_prefix":prefix,"format":"auto","codec":"auto"}},
    }, length

if __name__ == "__main__":
    wf, length = build("test")
    print("帧数:", length, "节点数:", len(wf))
    json.dump(wf, open(sys.argv[1] if len(sys.argv)>1 else "/dev/stdout","w"), ensure_ascii=False, indent=1)
