# -*- coding: utf-8 -*-
"""Figure cut-out on your own server over ssh: the transport for the core's matte.py.

The core's matte.py does everything else (frames from the rough cut, edge cleanup, the figure's box, source-edge cuts,
the check frame, place) and runs rembg on this computer. This command replaces only "run rembg and build the WebM":
the frames go to your server as JPG in one archive, rembg and the WebM packaging run there, one file comes back.

    python <core scripts>/addon.py matte cut edit/<id> --from 12.4 --to 19.0 [--width 720] [--name host] [--video <file>] [--host <ssh host>] [--dry]
    python <core scripts>/addon.py matte place edit/<id> ...      # the core's place (no server)

The server is an ssh host you reach without a password prompt (a key in your ssh agent or ~/.ssh/config). The script
only calls your ssh, scp and tar; it never handles keys or passwords. Settings, the first one found wins:
  host    --host, env REELS_MATTE_HOST, it-reelsmaker.json -> matte.host, then -> heavy_server (an older setting)
  rembg   --rembg, it-reelsmaker.json -> matte.server_rembg, then -> matte.rembg: the rembg command on the server,
          default "rembg" (on the server's PATH), or its full path, e.g. ~/venvs/rembg/bin/rembg
          (pip install "rembg[cpu,cli]" into a venv); server_rembg is for a project that also cuts out locally
  python  it-reelsmaker.json -> matte.server_python: a Python with Pillow on the server (the figure's box); default:
          the python next to rembg (rembg's venv has Pillow), otherwise python3
  e.g. in it-reelsmaker.json: {"matte": {"host": "my-server", "server_rembg": "~/venvs/rembg/bin/rembg"}}
The server needs Linux with rembg and its u2net_human_seg model, ffmpeg with libvpx-vp9, flock, timeout and free.
Frames go only to this host, into a temporary folder from mktemp that is removed afterwards. REELS_OFFLINE=1 blocks cut.
Speed: about 1 s per 1080x1920 frame on a small server's CPU at nice 19, plus about 45 s for the model start and the
transfer. Model: u2net_human_seg only (the core's allow-list). Before a run the server's free memory and disk are
checked. Queue: rembg and the WebM packaging run as one job under a server lock (flock /tmp/reels-matte.lock), so two
sessions never run the model at once; memory is checked again under the lock, leaving MEM_RESERVE for the server's
other services. --wait: how many minutes to wait for the queue (default 20); no turn in time -> exit code 1, the frames
on the server are removed.
"""
import importlib.util, json, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

try:  # core modules: on sys.path when run through the core's addon.py
    import reels_common
    from reels_common import project_settings, utf8_stdio, warn
except ImportError:
    sys.exit("run this through the it-reelsmaker core: python <core scripts>/addon.py matte ...")


def _core():
    """The core's matte.py, loaded by path from the core scripts folder (it is not on the import path as a package)."""
    name = "it_reelsmaker_matte_core"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(reels_common.__file__).resolve().parent / "matte.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


core = _core()
Fail = core.Fail
HOST = None           # --host, REELS_MATTE_HOST, it-reelsmaker.json -> matte.host / heavy_server (configure())
REMBG = "rembg"       # the rembg command on the server, quoted for its shell (configure())
REMBG_NAME = "rembg"  # the same as set by the person, for messages
PY = "python3"        # a Python with Pillow on the server, quoted for its shell (configure())
RDIR_RE = re.compile(r"^/tmp/matte\.[A-Za-z0-9]{6,}$")  # the temporary folder on the server: only from mktemp
HOST_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.@%:+\[\]-]{0,254}$")  # an ssh destination: no spaces, no leading -
LOCK = "/tmp/reels-matte.lock"  # one cut-out on the server at a time (all sessions, all videos)
# exit codes of the server job (remote_job)
RC_LOCK, RC_MEM, RC_EMPTY, RC_TIMEOUT = 74, 75, 76, 124


def ssh(cmd, check=True, timeout=3600, stdin=None):
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", HOST, cmd], capture_output=True, text=True, input=stdin,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise Fail(f"ssh {HOST}: {cmd[:80]}...\n{r.stderr[-1200:]}")
    return r


def _value(*vals):
    """The first value that is set; an unexpanded ${...} (a plugin setting left empty) counts as not set."""
    for v in vals:
        if v and not str(v).startswith("${"):
            return str(v).strip()
    return None


def remote_word(v):
    """A path or command for the server's shell, quoted; a leading ~/ or $HOME/ still means the home folder."""
    for pre in ("~/", "$HOME/", "${HOME}/"):
        if v.startswith(pre):
            return '"$HOME"/' + shlex.quote(v[len(pre):])
    return shlex.quote(v)


def configure(a):
    """The server settings: host, rembg and Python. Nothing here is secret: keys and passwords stay with your ssh
    client."""
    global HOST, REMBG, REMBG_NAME, PY
    s = project_settings()
    m = s.get("matte") if isinstance(s.get("matte"), dict) else {}
    host = _value(a.host, os.environ.get("REELS_MATTE_HOST"), m.get("host"), s.get("heavy_server"))
    if not host or host.lower() == "local":
        sys.exit("no server for the cut-out: set the host with --host <ssh host>, the REELS_MATTE_HOST environment "
                 "variable or {\"matte\": {\"host\": \"<ssh host>\"}} in it-reelsmaker.json. To cut out on this "
                 "computer instead: python <core scripts>/matte.py cut ...")
    if not HOST_RE.match(host):
        sys.exit(f"invalid ssh host {host!r}: a host name, an alias from ~/.ssh/config or user@host, without spaces")
    for tool in ("ssh", "scp", "tar"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is not found on this computer; the server cut-out needs an ssh client (ssh, scp) and tar")
    try:
        from reels_online import offline
    except ImportError:
        offline = lambda: os.environ.get("REELS_OFFLINE") == "1"
    if offline():
        sys.exit(f"REELS_OFFLINE=1: no network, and the cut-out sends frames to {host}")
    HOST = host
    REMBG_NAME = _value(a.rembg, m.get("server_rembg"), m.get("rembg")) or "rembg"
    REMBG = remote_word(REMBG_NAME)
    py = _value(m.get("server_python"))
    if not py:  # the python of rembg's venv has Pillow; a bare "rembg" command: python3 from the server's PATH
        py = REMBG_NAME.rsplit("/", 1)[0] + "/python" if "/" in REMBG_NAME else "python3"
    PY = remote_word(py)


def server_ok(n_mpx, model="u2net_human_seg"):
    """Free memory and disk on the server; None: go ahead, otherwise the reason."""
    why = core.model_ok(model)
    if why:
        return why
    need = core.MODEL_RAM[model]
    try:
        out = ssh("free -m | awk '/Mem:/{print $7}'; df -Pm /tmp | awk 'NR==2{print $4}'; command -v "
                  + REMBG + " >/dev/null && echo rembg", check=False, timeout=30).stdout.split()
    except Exception as ex:  # noqa: BLE001
        return f"server {HOST} is unreachable: {ex}"
    if "rembg" not in out or len(out) < 3:
        return (f"no rembg on {HOST} ({REMBG_NAME}), or the server did not answer: install it there (the core skill's "
                f"references/figure.md, section 1) or set matte.server_rembg to its full path")
    mem, disk = int(out[0]), int(out[1])
    if mem < need + core.MEM_RESERVE:
        return (f"{HOST} has {mem} MB of free memory; model {model} needs ~{need} + {core.MEM_RESERVE} MB of headroom: "
                f"wait and try again")
    if disk < n_mpx * 3 + 500:
        return f"{HOST} has {disk} MB free in /tmp: too little"
    return None


def remote_job(q, model, fps, limit, wait):
    """A script for the server: the queue (flock), a memory check under the lock, rembg and the WebM packaging.
    q: the job folder, already quoted; limit: the time limit for rembg, s; wait: how long to wait for the queue, s."""
    need = core.MODEL_RAM[model] + core.MEM_RESERVE
    sh = lambda args: " ".join(shlex.quote(str(x)) for x in args)
    job = "\n".join([
        f"cd {q} || exit 1",
        # memory under the lock: a previous cut-out has finished, but other services may have taken memory
        "avail=$(free -m | awk '/Mem:/{print $7}')",
        f'if [ "${{avail:-0}}" -lt {need} ]; then echo "free $avail MB, needed {need}" >&2; exit {RC_MEM}; fi',
        f"timeout -k 30 {int(limit)} nice -n 19 {REMBG} {sh(core.rembg_args(model, 'in', 'out'))} >rembg.log 2>&1 "
        "|| { rc=$?; tail -c 1200 rembg.log >&2; exit $rc; }",
        f"ls out/*.png >/dev/null 2>&1 || exit {RC_EMPTY}",
        "nice -n 19 " + sh(core.pack_cmd(fps, ["-pattern_type", "glob", "-i", "out/*.png"], "person.webm")),
    ])
    return f"flock -E {RC_LOCK} -w {int(wait)} {LOCK} sh -c {shlex.quote(job)}"


JOB_ERR = {RC_LOCK: "the server queue did not reach this job in {wait} min (another cut-out is running): try again "
                    "later or with a larger --wait",
           RC_MEM: "not enough memory on the server under the lock ({err}): wait and try again",
           RC_EMPTY: "rembg produced no frames",
           RC_TIMEOUT: "rembg did not finish in {limit} s: a shorter span or --width 720",
           137: "rembg was killed (the {limit} s limit or out of memory): a shorter span, --width 720, or later"}


def remote_cleanup(rdir):
    """Remove the temporary folder on the server and make sure it is gone. The path only from mktemp (RDIR_RE)."""
    if not rdir or not RDIR_RE.match(rdir):
        return
    q = shlex.quote(rdir)
    try:
        r = ssh(f"rm -rf -- {q}; test -e {q} && echo left || echo gone", check=False, timeout=60)
        if "gone" not in r.stdout:
            warn(f"could not remove {rdir} on {HOST} ({r.stderr.strip()[-200:]}): remove it by hand")
    except Exception as ex:  # noqa: BLE001
        warn(f"could not remove {rdir} on {HOST} ({ex}): remove it by hand")


class Server:
    """The engine for the core's cmd_cut: rembg and the WebM packaging on your server."""

    def __init__(self, a):
        configure(a)
        self.model = a.model
        self.rdir = None

    def check(self, n_mpx, model):
        return server_ok(n_mpx, model)

    def run(self, src, fps, limit, wait, dst):
        """JPG frames in src -> the server -> rembg + packaging there -> dst; -> the figure's box (the core's BBOX)."""
        # the temporary folder on the server: mktemp only, names from the command line never get into the path
        rdir = self.rdir = ssh("d=$(mktemp -d /tmp/matte.XXXXXXXX) && mkdir -p \"$d/in\" \"$d/out\" && echo \"$d\"",
                               timeout=30).stdout.strip().splitlines()[-1]
        if not RDIR_RE.match(rdir):
            raise Fail(f"the server returned an odd temporary folder: {rdir!r}")
        q = shlex.quote(rdir)
        tar = subprocess.Popen(["tar", "-C", str(src), "-cf", "-", "."], stdout=subprocess.PIPE)
        transfer = None
        try:
            transfer = subprocess.Popen(["ssh", "-o", "ConnectTimeout=10", HOST, f"tar -C {q}/in -xf -"],
                                        stdin=tar.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            tar.stdout.close()  # only the child owns the read end now
            stdout, stderr = transfer.communicate(timeout=300)
            tar.wait(timeout=30)
            r = subprocess.CompletedProcess(transfer.args, transfer.returncode, stdout, stderr)
        finally:
            tar.stdout.close()
            for proc in (transfer, tar):
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        if r.returncode != 0 or tar.returncode != 0:
            raise Fail("uploading the frames failed: " + r.stderr.decode("utf-8", "replace")[-300:])
        # rembg + packaging with edge cleanup on the server, in the queue (flock); memory checked again under the lock
        print(f"server {HOST}: queue {LOCK} (waiting up to {wait / 60:g} min), then rembg...", flush=True)
        r = ssh(remote_job(q, self.model, fps, limit, wait), check=False, timeout=wait + limit + 300)
        if r.returncode != 0:
            err = r.stderr.strip()[-600:]
            raise Fail(JOB_ERR.get(r.returncode, "rembg/ffmpeg failed on the server (code {rc}): {err}").format(
                wait=f"{wait / 60:g}", err=err, limit=round(limit), rc=r.returncode))
        info = json.loads(ssh(f"{PY} - {q}/out", stdin=core.BBOX).stdout.strip().splitlines()[-1])
        if not info["frames"]:
            raise Fail("rembg produced no frames")
        r = subprocess.run(["scp", "-q", f"{HOST}:{rdir}/person.webm", str(dst)], capture_output=True, timeout=300)
        if r.returncode != 0:
            raise Fail("downloading the webm failed: " + r.stderr.decode("utf-8", "replace")[-300:])
        return info

    def cleanup(self):
        remote_cleanup(self.rdir)


def main(argv=None):
    utf8_stdio()
    ap, cut = core.parser("addon.py matte", __doc__)
    for act in cut._actions:
        if act.dest == "wait":
            act.help = "minutes to wait for the server queue (flock)"
        elif act.dest == "rembg":
            act.help = ("the rembg command or its full path on the server (default: matte.server_rembg, then "
                        "matte.rembg, then rembg)")
    cut.add_argument("--host", help="ssh host of your server (default: REELS_MATTE_HOST, then matte.host or "
                                    "heavy_server in it-reelsmaker.json)")
    cut.set_defaults(fn=lambda a: core.cmd_cut(a, Server))
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
