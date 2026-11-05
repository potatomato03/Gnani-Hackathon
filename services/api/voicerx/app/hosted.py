"""Separate HTTP instances from Vercel's durable, continuously running worker daemon."""
import os
import signal
import sys
import threading


def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'api'
    if mode=='api':
        os.environ['APP_RUN_WORKER']='0'
        import uvicorn
        uvicorn.run('voicerx.app.main:app',host='0.0.0.0',port=int(os.environ.get('PORT','80')),
                    access_log=False,proxy_headers=True,forwarded_allow_ips=os.environ.get('FORWARDED_ALLOW_IPS','127.0.0.1'))
    elif mode=='worker':
        from .config import load_settings
        from .db import open_pool,close_pool
        from .followup import FollowupService
        from .worker import Worker
        settings=load_settings();open_pool(settings.database_url)
        from ..exports.pdf.render import html_to_pdf
        settings.artifacts_dir.mkdir(parents=True,exist_ok=True)
        probe=html_to_pdf('<!doctype html><meta charset="utf-8"><p>Private report renderer ready.</p>',
                          settings.artifacts_dir/'renderer-check.pdf')
        if not probe.read_bytes().startswith(b'%PDF'):
            raise RuntimeError('PDF renderer startup verification failed.')
        print('Private worker startup verified: database and PDF renderer ready.',flush=True)
        # Load the medicine name index now, not inside the first visit after a deploy (runbook D-136).
        from .main import warm_up
        warm_up()
        print('Medicine index loaded.',flush=True)
        worker=Worker(settings,followup=FollowupService(settings))
        stop=threading.Event()
        def shutdown(*_):
            stop.set();worker.stop()
        signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
        worker.start()
        try:
            while not stop.wait(1):
                if not worker.is_alive():
                    raise RuntimeError('Worker stopped unexpectedly.')
        finally:
            worker.stop();worker.join(timeout=240);close_pool()
    else:
        raise SystemExit('Expected api or worker.')


if __name__=='__main__':
    main()
