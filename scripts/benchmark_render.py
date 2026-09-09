import os
import sys
import time
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH_DIR = os.path.join(PROJECT_ROOT, "scratch")
DATE_STR = "20260909"
STORY_NUM = "1"

audio_path = os.path.join(PROJECT_ROOT, f"audio/{DATE_STR}/voice_{STORY_NUM}.wav")
timing_path = os.path.join(PROJECT_ROOT, f"audio/{DATE_STR}/voice_{STORY_NUM}_timing.json")
subtitle_path = os.path.join(PROJECT_ROOT, f"subtitles/{DATE_STR}_{STORY_NUM}_short.ass")
card_path = os.path.join(PROJECT_ROOT, f"reddit_stories/{DATE_STR}/card_{STORY_NUM}.png")
music_path = os.path.join(PROJECT_ROOT, "assets/music/emotional_a_stroll.mp3")

with open(timing_path, "r", encoding="utf-8") as f:
    tdata = json.load(f)
title_end_time = float(tdata.get("title_end_time", 3.0))
msg_timings = tdata.get("message_timings", [])

# Find chat step images
step_entries = []
k = 0
while True:
    p = os.path.join(PROJECT_ROOT, f"reddit_stories/{DATE_STR}/chat_{STORY_NUM}_step_{k}.png")
    if os.path.exists(p):
        step_entries.append(p)
        k += 1
    else:
        break

# Get audio duration
cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
audio_dur = float(subprocess.check_output(cmd, text=True).strip())
print(f"[BENCHMARK] Audio Duration: {audio_dur:.2f}s, Title End: {title_end_time:.2f}s, Chat Steps: {len(step_entries)}")

# Slices for gameplay (9 slices)
slices = [
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video2.mp4"), 889.70, 11.48),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video1.mp4"), 223.30, 9.80),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video7.mp4"), 1070.18, 10.24),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video6.mp4"), 187.40, 10.50),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video3.mp4"), 891.42, 12.46),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video4.mp4"), 168.20, 13.15),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video6.mp4"), 390.16, 9.51),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video3.mp4"), 382.29, 13.96),
    (os.path.join(PROJECT_ROOT, "assets/gameplays/video2.mp4"), 748.50, 11.61),
]

def build_gameplay_inputs_and_filters():
    g_inputs = []
    g_filters = []
    g_labels = []
    for i, (cp, in_pt, slen) in enumerate(slices):
        g_inputs.extend(["-ss", f"{in_pt:.2f}", "-t", f"{slen:.2f}", "-avoid_negative_ts", "make_zero", "-i", cp.replace("\\", "/")])
        g_filters.append(f"[{i}:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,setpts=PTS-STARTPTS[v_{i}]")
        g_labels.append(f"[v_{i}]")
    concat_filter = f"{';'.join(g_filters)};{''.join(g_labels)}concat=n={len(slices)}:v=1:a=0[gameplay]"
    return g_inputs, concat_filter, len(slices)

def run_test(name, cmd):
    print(f"\n==========================================")
    print(f"STARTING {name}")
    print(f"==========================================")
    t0 = time.time()
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    t1 = time.time()
    elapsed = t1 - t0
    if p.returncode != 0:
        print(f"[FAILED] {name} exited with {p.returncode}:\n{p.stderr[-500:]}")
        return elapsed, False
    print(f"[SUCCESS] {name} completed in {elapsed:.2f}s ({elapsed/60.0:.2f} min)")
    return elapsed, True

# ----------------------------------------------------
# TEST 1: Gameplay + Title Card + Subs + Audio (Baseline)
# ----------------------------------------------------
def benchmark_test_1():
    out_file = os.path.join(SCRATCH_DIR, "bench_t1.mp4")
    g_inputs, g_filter, num_g = build_gameplay_inputs_and_filters()
    card_idx = num_g
    voice_idx = num_g + 1
    music_idx = num_g + 2
    
    cmd = ["ffmpeg", "-y"] + g_inputs
    cmd += ["-loop", "1", "-t", f"{title_end_time + 2.0:.2f}", "-i", card_path.replace("\\", "/")]
    cmd += ["-i", audio_path.replace("\\", "/")]
    cmd += ["-stream_loop", "10", "-t", f"{audio_dur + 2.0:.2f}", "-i", music_path.replace("\\", "/")]
    
    sub_path_esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
    v_f = [
        g_filter,
        f"[{card_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuva420p,fade=t=out:st={title_end_time-0.35:.2f}:d=0.35:alpha=1[card]",
        f"[gameplay][card]overlay=0:0:enable='between(t,0,{title_end_time:.2f})':eof_action=pass[v_card]",
        f"[v_card]subtitles='{sub_path_esc}'[v_out]"
    ]
    a_f = [
        f"[{voice_idx}:a]volume=0.220,asplit=2[v_main][v_sc];"
        f"[{music_idx}:a]atrim=0:{audio_dur:.2f},asetpts=PTS-STARTPTS,volume=0.030[m_vol];"
        f"[m_vol][v_sc]sidechaincompress=threshold=0.008:ratio=8:attack=150:release=650:makeup=1[m_ducked];"
        f"[v_main][m_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
    ]
    
    fc = ";".join(v_f) + ";" + ";".join(a_f)
    cmd += [
        "-filter_complex", fc,
        "-map", "[v_out]", "-map", "[a_out]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-t", f"{audio_dur:.2f}",
        out_file
    ]
    return run_test("TEST 1 (Gameplay + Title + Subs + Audio)", cmd)

# ----------------------------------------------------
# TEST 2: Gameplay + Title + 16 Separate PNG Overlays + Subs + Audio (Current Way)
# ----------------------------------------------------
def benchmark_test_2():
    out_file = os.path.join(SCRATCH_DIR, "bench_t2.mp4")
    g_inputs, g_filter, num_g = build_gameplay_inputs_and_filters()
    card_idx = num_g
    
    step_indices = []
    curr_idx = num_g + 1
    step_inputs = []
    for s_p in step_entries:
        step_inputs.extend(["-loop", "1", "-t", f"{audio_dur + 2.0:.2f}", "-i", s_p.replace("\\", "/")])
        step_indices.append(curr_idx)
        curr_idx += 1
        
    voice_idx = curr_idx
    music_idx = curr_idx + 1
    
    cmd = ["ffmpeg", "-y"] + g_inputs
    cmd += ["-loop", "1", "-t", f"{title_end_time + 2.0:.2f}", "-i", card_path.replace("\\", "/")]
    cmd += step_inputs
    cmd += ["-i", audio_path.replace("\\", "/")]
    cmd += ["-stream_loop", "10", "-t", f"{audio_dur + 2.0:.2f}", "-i", music_path.replace("\\", "/")]
    
    sub_path_esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
    v_f = [
        g_filter,
        f"[{card_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuva420p,fade=t=out:st={title_end_time-0.35:.2f}:d=0.35:alpha=1[card]",
        f"[gameplay][card]overlay=0:0:enable='between(t,0,{title_end_time:.2f})':eof_action=pass[v_0]"
    ]
    
    last_v = "v_0"
    for s_i, s_idx in enumerate(step_indices):
        m_start = float(msg_timings[s_i]["start"]) if s_i < len(msg_timings) else (title_end_time + s_i * 4.0)
        m_end = float(msg_timings[s_i+1]["start"]) if (s_i + 1 < len(msg_timings)) else (audio_dur - 1.0)
        out_v = f"v_step_{s_i}"
        v_f.append(f"[{last_v}][{s_idx}:v]overlay=0:0:enable='between(t,{m_start:.2f},{m_end:.2f})':eof_action=pass[{out_v}]")
        last_v = out_v
        
    v_f.append(f"[{last_v}]subtitles='{sub_path_esc}'[v_out]")
    
    a_f = [
        f"[{voice_idx}:a]volume=0.220,asplit=2[v_main][v_sc];"
        f"[{music_idx}:a]atrim=0:{audio_dur:.2f},asetpts=PTS-STARTPTS,volume=0.030[m_vol];"
        f"[m_vol][v_sc]sidechaincompress=threshold=0.008:ratio=8:attack=150:release=650:makeup=1[m_ducked];"
        f"[v_main][m_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
    ]
    
    fc = ";".join(v_f) + ";" + ";".join(a_f)
    cmd += [
        "-filter_complex", fc,
        "-map", "[v_out]", "-map", "[a_out]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-t", f"{audio_dur:.2f}",
        out_file
    ]
    return run_test("TEST 2 (Gameplay + Title + 16 PNG Overlays + Subs + Audio)", cmd)

# ----------------------------------------------------
# TEST 3: Gameplay + Title + ONE Pre-composed Dialogue Layer + Subs + Audio
# ----------------------------------------------------
def benchmark_test_3():
    out_file = os.path.join(SCRATCH_DIR, "bench_t3.mp4")
    
    # Step A: Create 1 transparent blank PNG for initial silence (t=0..t_first)
    blank_png = os.path.join(SCRATCH_DIR, "blank_transparent.png")
    if not os.path.exists(blank_png):
        from PIL import Image
        img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        img.save(blank_png)
        
    # Step B: Build concat demuxer text file
    t_first = float(msg_timings[0]["start"]) if msg_timings else title_end_time
    txt_path = os.path.join(SCRATCH_DIR, "dialogue_timeline.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"ffconcat version 1.0\n")
        f.write(f"file '{blank_png.replace(chr(92), '/')}'\n")
        f.write(f"duration {t_first:.2f}\n")
        for s_i, s_p in enumerate(step_entries):
            m_start = float(msg_timings[s_i]["start"]) if s_i < len(msg_timings) else (title_end_time + s_i * 4.0)
            m_end = float(msg_timings[s_i+1]["start"]) if (s_i + 1 < len(msg_timings)) else (audio_dur)
            dur = max(0.1, m_end - m_start)
            f.write(f"file '{s_p.replace(chr(92), '/')}'\n")
            f.write(f"duration {dur:.2f}\n")
        # repeat last file per ffconcat spec
        f.write(f"file '{step_entries[-1].replace(chr(92), '/')}'\n")

    # Step C: Master Render with ONE Dialogue Layer input
    g_inputs, g_filter, num_g = build_gameplay_inputs_and_filters()
    card_idx = num_g
    dialogue_idx = num_g + 1
    voice_idx = num_g + 2
    music_idx = num_g + 3
    
    cmd = ["ffmpeg", "-y"] + g_inputs
    cmd += ["-loop", "1", "-t", f"{title_end_time + 2.0:.2f}", "-i", card_path.replace("\\", "/")]
    cmd += ["-f", "concat", "-safe", "0", "-i", txt_path.replace("\\", "/")]
    cmd += ["-i", audio_path.replace("\\", "/")]
    cmd += ["-stream_loop", "10", "-t", f"{audio_dur + 2.0:.2f}", "-i", music_path.replace("\\", "/")]
    
    sub_path_esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
    v_f = [
        g_filter,
        f"[{card_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuva420p,fade=t=out:st={title_end_time-0.35:.2f}:d=0.35:alpha=1[card]",
        f"[gameplay][card]overlay=0:0:enable='between(t,0,{title_end_time:.2f})':eof_action=pass[v_card]",
        f"[{dialogue_idx}:v]format=yuva420p[dialogue_stream]",
        f"[v_card][dialogue_stream]overlay=0:0:eof_action=pass[v_dialogue]",
        f"[v_dialogue]subtitles='{sub_path_esc}'[v_out]"
    ]
    
    a_f = [
        f"[{voice_idx}:a]volume=0.220,asplit=2[v_main][v_sc];"
        f"[{music_idx}:a]atrim=0:{audio_dur:.2f},asetpts=PTS-STARTPTS,volume=0.030[m_vol];"
        f"[m_vol][v_sc]sidechaincompress=threshold=0.008:ratio=8:attack=150:release=650:makeup=1[m_ducked];"
        f"[v_main][m_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
    ]
    
    fc = ";".join(v_f) + ";" + ";".join(a_f)
    cmd += [
        "-filter_complex", fc,
        "-map", "[v_out]", "-map", "[a_out]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-t", f"{audio_dur:.2f}",
        out_file
    ]
    return run_test("TEST 3 (Gameplay + Title + ONE Dialogue Layer + Subs + Audio)", cmd)

if __name__ == "__main__":
    t1_time, t1_ok = benchmark_test_1()
    t2_time, t2_ok = benchmark_test_2()
    t3_time, t3_ok = benchmark_test_3()
    
    print("\n" + "="*50)
    print("FINAL BENCHMARK COMPARISON RESULTS")
    print("="*50)
    print(f"Test 1 (Baseline: Gameplay + Card + Subs + Audio): {t1_time:.2f}s ({t1_time/60.0:.2f} min) [OK: {t1_ok}]")
    print(f"Test 2 (16 PNG Overlays):                         {t2_time:.2f}s ({t2_time/60.0:.2f} min) [OK: {t2_ok}]")
    print(f"Test 3 (1 Consolidated Dialogue Layer):           {t3_time:.2f}s ({t3_time/60.0:.2f} min) [OK: {t3_ok}]")
    print("="*50)
