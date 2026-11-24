"""TEMP diagnostic for the Windows rate failure: prints raw loud spans and the speech mask of the test's sound."""
import subprocess, sys, tempfile, os
S = os.path.join(os.path.dirname(__file__), "..", "plugins", "it-reelsmaker", "skills", "it-reelsmaker", "scripts")
sys.path.insert(0, S)
import speech_mask as sm
d = tempfile.mkdtemp()
w, m = os.path.join(d, "speech.wav"), os.path.join(d, "final.mp4")
run = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
run("-f", "lavfi", "-i", "sine=f=300:d=2.5,volume='if(between(t,0.2,0.7)+between(t,0.8,1.8),1,0)':eval=frame", "-ar", "16000", w)
run("-f", "lavfi", "-i", "color=c=gray:s=180x320:r=30:d=2.5", "-i", w, "-shortest", "-c:v", "libx264", "-c:a", "aac", m)
def spans(x):
    out, i = [], 0
    while i < len(x):
        if x[i]:
            j = i
            while j < len(x) and x[j]: j += 1
            out.append((round(i * sm.HOP, 2), round(j * sm.HOP, 2))); i = j
        else: i += 1
    return out
for f in (w, m):
    env, hf = sm.load_envs(f)
    sdb = sm.smax(env); srt = sorted(x for x in sdb if x > -90)
    thr = min(-30.0, (srt[int(len(srt) * 0.95)] if srt else -20) - 20)
    vl = sm.voiceless(hf)
    print(os.path.basename(f), "n", len(env), "thr", round(thr, 1), "raw", spans([x >= thr for x in env]),
          "vl", spans(vl), "mask", spans(sm.speech_mask(sdb, thr, vl=vl)), "novl", spans(sm.speech_mask(sdb, thr)))
    print("  env 0.6-0.9:", [round(x) for x in env[60:90]])
    print("  env 1.75-1.95:", [round(x) for x in env[175:195]])
print(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time,duration", "-of", "compact", m], capture_output=True, text=True).stdout)
