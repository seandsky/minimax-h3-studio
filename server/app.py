"""MiniMax-H3 Studio HTTP entry point and application wiring."""

import logging
from aiohttp import web
from remote_engine import RemoteEngine
from h3_jobs import JobStore
from model_catalog import LEGACY_PRESETS
from server_settings import ServerSettings
from job_worker import Worker
from http_api import system, jobs, submissions, frontend


def make_app(settings=None, engine=None, *, start_worker=True):
    settings = settings or ServerSettings.from_env()
    settings.prepare_directories()
    store = JobStore(settings.data / "jobs.db")
    store.backfill_lora(LEGACY_PRESETS)
    store.fail_running("server restarted while the job was running")
    if engine is None and not settings.comfy_url:
        from h3_engine import H3Engine
    engine = (
        engine
        if engine is not None
        else RemoteEngine(settings.comfy_url, settings.workflows) if settings.comfy_url
        else H3Engine(settings.comfyui, settings.comfy_args, audio_settings=settings)
    )
    worker = Worker(store, engine, settings)
    app = web.Application(client_max_size=256 * 1024**2)
    app["settings"], app["store"], app["worker"] = settings, store, worker
    app.router.add_get("/api/health", system.health)
    app.router.add_get("/api/presets", system.presets)
    app.router.add_get("/api/jobs", jobs.list_jobs)
    app.router.add_post("/api/jobs", submissions.create_job)
    app.router.add_get("/api/jobs/{id}", jobs.get_job)
    app.router.add_post("/api/jobs/{id}/cancel", jobs.cancel_job)
    app.router.add_post("/api/jobs/{id}/upscale", jobs.upscale_job)
    app.router.add_post("/api/unload", system.unload)
    app.router.add_delete("/api/jobs/{id}", jobs.delete_job)
    for name, folder in (
        ("models3d", settings.models3d),
        ("videos", settings.videos),
        ("pictures", settings.pictures),
        ("music", settings.music),
        ("thumbs", settings.thumbs),
        ("uploads", settings.uploads),
        ("speech", settings.speech),
        ("transcripts", settings.transcripts),
        ("llm", settings.llm),
    ):
        app.router.add_static(f"/files/{name}", folder)
    app.router.add_get("/{path:.*}", frontend.frontend)

    if start_worker:

        async def start(_app):
            worker.start()

        app.on_startup.append(start)
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = ServerSettings.from_env()
    if settings.comfyui is None and not settings.comfy_url:
        raise SystemExit("set H3_COMFYUI to the ComfyUI checkout")
    app = make_app(settings)
    app["worker"].engine.bootstrap()
    web.run_app(app, host=settings.host, port=settings.port, access_log=None)
