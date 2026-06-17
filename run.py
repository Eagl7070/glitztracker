#!/usr/bin/env python3
"""
GlitzTracker entrypoint — runs gunicorn web server + background checker.
Works whether files are in app/ subfolder or at root level.
"""
import os, sys, time, signal, subprocess, logging

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("main")

PORT     = os.environ.get("PORT", "8000")
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
children = {}
stopping = False


def spawn(name, cmd):
    env = os.environ.copy()
    proc = subprocess.Popen(cmd, env=env, cwd=ROOT_DIR)
    children[name] = proc
    log.info("Started %s (pid %d)", name, proc.pid)


def shutdown(sig, frame):
    global stopping
    stopping = True
    log.info("Shutting down…")
    for p in children.values():
        try: p.terminate()
        except: pass


def main():
    for sig in (signal.SIGTERM, signal.SIGINT):
        try: signal.signal(sig, shutdown)
        except ValueError: pass

    spawn("web",     [sys.executable, "-m", "gunicorn", "wsgi:app",
                      "--bind", f"0.0.0.0:{PORT}",
                      "--workers", "2", "--timeout", "120"])
    spawn("checker", [sys.executable, "checker.py"])

    backoff = {}
    while not stopping:
        time.sleep(5)
        for name, proc in list(children.items()):
            if proc.poll() is not None:
                wait = min(backoff.get(name, 5) * 2, 60)
                backoff[name] = wait
                log.warning("%s exited (code %d); restarting in %ds",
                            name, proc.returncode, wait)
                time.sleep(wait)
                if not stopping:
                    spawn(name, proc.args)

    deadline = time.time() + 10
    for p in children.values():
        try: p.wait(timeout=max(0, deadline - time.time()))
        except: p.kill()


if __name__ == "__main__":
    main()
