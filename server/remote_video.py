"""Build API-format H3 graphs from the Studio video form."""
from model_catalog import CLIP, VIDEO_VAE, AUDIO_VAE, LORAS, unet_file, frame_count, fixed_sampling


def video_graph(v):
    graph = {}
    def node(kind, **inputs):
        key = str(len(graph) + 1)
        graph[key] = {'class_type': kind, 'inputs': inputs}
        return [key, 0]
    p = LORAS[v['lora']]
    if fixed_sampling(v['lora']):
        v = {**v, 'sampler': None, 'steps': None}
    model = node('UNETLoader', unet_name=unet_file(v['lora']), weight_dtype='default')
    model = node('MiniMaxH3SigmaShift', model=model, shift_video=p['shift_video'], shift_audio=p['shift_audio'])
    if p['loader'] == 'larryvrh':
        model = node('MiniMaxH3TurboLoRA', model=model, lora_name=p['file'], strength=v['lora_strength'])
        sampler = node('MiniMaxH3TurboSampler')
    else:
        if p.get('file'):
            model = node('LoraLoaderModelOnly', model=model, lora_name=p['file'], strength_model=v['lora_strength'])
        sampler = node('KSamplerSelect', sampler_name=v.get('sampler') or p.get('sampler', 'euler'))
    if p.get('vsa') or p.get('sol'):
        model = node('ModelAttentionBackend', model=model, attention='comfy kitchen attention')
        selection = {'selection': 'vsa', 'keep_percent': p['vsa']['keep']} if p.get('vsa') else {'selection': 'sol-attn', 'tau': p['sol']['tau']}
        model = node('BlockSparseAttention', model=model, selection=selection,
                     start_percent=(p.get('vsa') or p['sol'])['start'], end_percent=1.0,
                     dense_blocks='', min_tokens=12288, extra_tokens=256, sink_conditioning='exact_kv_and_rows')
    clip = node('CLIPLoader', clip_name=CLIP, type='minimax', device='default')
    vae = node('VAELoader', vae_name=VIDEO_VAE)
    audio_vae = node('VAELoader', vae_name=AUDIO_VAE)
    inputs = dict(clip=clip, vae=vae, prompt=v['prompt'], width=v['width'], height=v['height'], length=frame_count(v['duration']))
    if p['family'] == 'ref2va':
        # Dynamic input groups follow ComfyUI's API representation.
        inputs.update(audio_vae=audio_vae, ref_image_size='match')
        inputs['ref_images'] = {f'ref_image_{i}': node('LoadImage', image=name) for i, name in enumerate(v['ref_paths'], 1)}
        inputs['ref_videos'] = {}
        inputs['ref_video_audios'] = {}
        for i, name in enumerate(v['ref_video_paths'], 1):
            video = node('LoadVideo', file=name)
            components = node('GetVideoComponents', video=video)
            inputs['ref_videos'][f'ref_video_{i}'] = components
            inputs['ref_video_audios'][f'ref_video_audio_{i}'] = [components[0], 1]
        cond = node('MiniMaxH3ReferenceToVideo', **inputs)
    else:
        for key, name in [('first_frame', 'image_path'), ('last_frame', 'last_image_path')]:
            if v.get(name):
                inputs[key] = node('LoadImage', image=v[name])
        cond = node('MiniMaxH3ImageToVideo', **inputs)
    latent = [cond[0], 1]
    if v.get('audio_path'):
        audio = node('LoadAudio', audio=v['audio_path'])
        if v.get('audio_start'):
            audio = node('TrimAudioDuration', audio=audio, start_index=v['audio_start'], duration=v['duration'])
        cond = node('MiniMaxH3AddGuide', positive=cond, latent=latent, frame_idx=0, audio_vae=audio_vae, audio=audio)
    if p.get('sigmas'):
        sigmas = node('ManualSigmas', sigmas=', '.join(map(str, p['sigmas'])))
    else:
        sigmas = node('BasicScheduler', model=model, scheduler='simple', steps=v.get('steps') or p['steps'], denoise=1.0)
    samples = node('SamplerCustomAdvanced', noise=node('RandomNoise', noise_seed=v['seed']),
                   guider=node('BasicGuider', model=model, conditioning=cond), sampler=sampler, sigmas=sigmas, latent_image=latent)
    video = node('CreateVideo', images=node('VAEDecode', samples=samples, vae=vae), fps=24.0,
                 audio=node('VAEDecodeAudio', samples=samples, vae=audio_vae))
    node('SaveVideo', video=video, filename_prefix='studio/video', format={'format': 'mp4', 'codec': {'codec': 'h264'}})
    return graph
