import os
import subprocess
import glob

def probe():
    out_dir = "/home/ubuntu/narrateloop/output/20260907"
    for path in sorted(glob.glob(os.path.join(out_dir, "final_*.mp4"))):
        size = os.path.getsize(path) / (1024 * 1024)
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        try:
            dur = float(subprocess.check_output(cmd).decode().strip())
        except Exception as e:
            dur = str(e)
        print(f"{os.path.basename(path)}: Size={size:.2f}MB, Duration={dur}s")

if __name__ == "__main__":
    probe()
