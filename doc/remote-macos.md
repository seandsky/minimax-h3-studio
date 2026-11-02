# macOS with remote ComfyUI

Run `./start-macos.sh` from the repository. Requires Python 3.10+, Node 18+,
and network access for the initial dependency installation. No CUDA, torch,
local ComfyUI checkout, SSH, or container access is required.

Set H3_COMFY_URL and H3_PORT in your private `.env` before starting.
Open `http://<studio-host>:<studio-port>` from your trusted network.
Keep this unauthenticated workbench on a trusted network.

Configuration (in `.env`):

| Setting | Purpose |
| --- | --- |
| H3_COMFY_URL | Remote ComfyUI HTTP origin |
| H3_HOST | Studio bind address; default 0.0.0.0 |
| H3_PORT | Studio port; configure privately |
| H3_WORKFLOWS | API workflow directory; default ./workflows |

Video tasks build a remote H3 graph using the selected models and settings.
Missing models/nodes fail the individual job, not Studio startup. Files are
uploaded to remote ComfyUI and saved results are downloaded into local data/.
Remote files remain on the ComfyUI host. Progress is reported by stage while
polling history; percentage sampling updates are not available.

Cancel removes a waiting remote prompt and stops local waiting. Already running
remote inference continues: the shared `/interrupt` endpoint is intentionally
not called because it could interrupt another client's task. Unload is likewise
local only. Restarting Studio marks unfinished local jobs failed; it does not
stop remote work.

## Workflow overrides and other tasks

Export an **API-format** workflow from ComfyUI, not a UI workflow. Place its
node dictionary in `workflows/t2v.json`, `i2v.json`, `fl2v.json`, or `r2v.json`
to override the built-in graph. This is also the integration point for different
node versions. Other pipelines require these templates:
`image-moss.json`, `image-flux-klein-4b.json`, `image-qwen-image-21-turbo.json` (use the image model ID
from /api/presets), `music.json`, `3d.json`, `seedvr2.json`, `flashvsr.json`,
and `speech.json`. Remote ASR transcript export and Strata LLM are not supported.

Replace a node input value with an exact placeholder such as `${prompt}`,
`${width}`, `${height}`, `${duration}`, `${seed}`, `${steps}` or `${lora_strength}`.
Values retain their JSON types; embedded string interpolation is not supported.
Parameter names match the corresponding Worker engine call in server/job_worker.py.
`image_path`, `last_image_path`, `audio_path`, `source_path`, `ref_paths` and
`ref_video_paths` become remote uploaded filenames (lists for plural parameters).
Output path arguments are local destinations, not workflow placeholders.
Templates must include a Save node exposing output files in history. Avoid
multiple saved files of the same media type: the first matching artifact is used.

Generation has not been validated against installed H3 models. Node input
schemas may require workflow overrides when the remote ComfyUI version differs.

## Docker on the Mac Mini

Run `docker compose up -d --build` in the repository on the Mac Mini.
The image builds the frontend and runs only the HTTP adapter (no GPU packages).
Set H3_COMFY_URL and H3_PUBLISH_PORT in your private `.env` first.
Open `http://<studio-host>:<published-port>`. No real endpoint is included
in the repository. The container uses a generic internal application port.
`./data` persists jobs/uploads/results and `./workflows` persists API templates.
Inspect with `docker compose logs -f studio`; stop with `docker compose down`.
Docker Desktop must be running; the container restarts with Docker unless stopped.
