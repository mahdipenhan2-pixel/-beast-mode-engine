#!/usr/bin/env python3
import subprocess
import tempfile
import sys
import json
from pathlib import Path
from fractions import Fraction
# ==========================================
# BEAST MODE V1.3 — AUTOMATIC QUALITY CONTROL
# ==========================================
ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
AUDIO_DIR = ROOT / "audio"
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "BEAST-MODE-FINAL.mp4"
MUSIC_FILE = AUDIO_DIR / "music.mp3"
WATERMARK_FILE = ASSETS_DIR / "watermark.png"
# VIDEO SETTINGS
WIDTH = 1080
HEIGHT = 1920
FPS = 30
# AUDIO SETTINGS
MUSIC_VOLUME = 0.22
ORIGINAL_AUDIO_VOLUME = 1.0
# CINEMATIC COLOR SETTINGS
COLOR_CONTRAST = 1.06
COLOR_BRIGHTNESS = 0.01
COLOR_SATURATION = 1.08
COLOR_GAMMA = 1.02
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
# QUALITY CONTROL
DURATION_TOLERANCE = 1.5
# ==========================================
# COMMAND RUNNER
# ==========================================
def run(command):
    print("\nRunning:", " ".join(map(str, command)))
    subprocess.run(
        command,
        check=True
    )
# ==========================================
# CHECK REQUIREMENTS
# ==========================================
def check_ffmpeg():
    for executable in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run(
                [executable, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                f"{executable} is not installed."
            )
# ==========================================
# VIDEO INFORMATION
# ==========================================
def get_media_info(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)
def get_duration(path):
    info = get_media_info(path)
    duration = float(
        info["format"]["duration"]
    )
    if duration <= 0:
        raise RuntimeError("Invalid video duration.")
    return duration
def has_audio(path):
    info = get_media_info(path)
    return any(
        stream.get("codec_type") == "audio"
        for stream in info.get("streams", [])
    )
# ==========================================
# CINEMATIC VIDEO NORMALIZATION
# ==========================================
def normalize_clip(source, destination):
    duration = get_duration(source)
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"fps={FPS},"
        "setsar=1,"
        f"eq=contrast={COLOR_CONTRAST}:"
        f"brightness={COLOR_BRIGHTNESS}:"
        f"saturation={COLOR_SATURATION}:"
        f"gamma={COLOR_GAMMA}"
    )
    command = [
        "ffmpeg", "-y",
        "-i", str(source)
    ]
    if has_audio(source):
        command += [
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-vf", video_filter,
            "-af", "aresample=48000,apad"
        ]
    else:
        command += [
            "-f", "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", video_filter
        ]
    command += [
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-movflags", "+faststart",
        str(destination)
    ]
    run(command)
# ==========================================
# CLIP ORDER
# ==========================================
def create_concat_file(clips, concat_file):
    with concat_file.open(
        "w",
        encoding="utf-8"
    ) as file:
        for clip in clips:
            safe_path = (
                str(clip)
                .replace("\\", "/")
                .replace("'", "'\\''")
            )
            file.write(
                f"file '{safe_path}'\n"
            )
# ==========================================
# AUDIO MIXING + FINAL VIDEO
# ==========================================
def render_final_video(video_file, duration):
    fade_duration = min(2.0, duration)
    fade_start = max(0.0, duration - fade_duration)
    audio_filter = (
        f"[0:a]volume={ORIGINAL_AUDIO_VOLUME}[original];"
        f"[1:a]volume={MUSIC_VOLUME},"
        f"atrim=duration={duration},"
        "asetpts=PTS-STARTPTS[music];"
        "[original][music]"
        "amix=inputs=2:duration=first:"
        "dropout_transition=2:normalize=0,"
        "alimiter=limit=0.95,"
        f"afade=t=out:st={fade_start}:d={fade_duration}"
        "[audio]"
    )
    command = [
        "ffmpeg", "-y",
        "-i", str(video_file),
        "-stream_loop", "-1",
        "-i", str(MUSIC_FILE)
    ]
    if WATERMARK_FILE.exists():
        command += [
            "-i", str(WATERMARK_FILE),
            "-filter_complex",
            audio_filter +
            ";[0:v][2:v]overlay=W-w-45:H-h-70[video]",
            "-map", "[video]",
            "-map", "[audio]"
        ]
    else:
        command += [
            "-filter_complex", audio_filter,
            "-map", "0:v:0",
            "-map", "[audio]"
        ]
    command += [
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-shortest",
        str(OUTPUT_FILE)
    ]
    run(command)
# ==========================================
# AUTOMATIC QUALITY CONTROL
# ==========================================
def quality_control(expected_duration):
    print("\n================================")
    print("BEAST MODE AUTOMATIC QC")
    print("================================")
    results = []
    def report(name, passed, detail):
        status = "PASS" if passed else "FAIL"
        results.append(passed)
        print(
            f"[{status}] {name}: {detail}"
        )
    if not OUTPUT_FILE.is_file():
        raise RuntimeError(
            "QC FAILED: Output file does not exist."
        )
    file_size = OUTPUT_FILE.stat().st_size
    report(
        "File existence",
        file_size > 0,
        f"{file_size / (1024 * 1024):.2f} MB"
    )
    info = get_media_info(OUTPUT_FILE)
    streams = info.get("streams", [])
    video_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "audio"
    ]
    if not video_streams:
        raise RuntimeError(
            "QC FAILED: No video stream found."
        )
    video = video_streams[0]
    audio_present = len(audio_streams) > 0
    report(
        "Audio stream",
        audio_present,
        "Audio detected" if audio_present else "No audio found"
    )
    resolution_ok = (
        video.get("width") == WIDTH
        and video.get("height") == HEIGHT
    )
    report(
        "Resolution",
        resolution_ok,
        f"{video.get('width')}x{video.get('height')}"
    )
    frame_rate = Fraction(
        video.get("avg_frame_rate", "0/1")
    )
    fps_ok = float(frame_rate) == FPS
    report(
        "Frame rate",
        fps_ok,
        f"{float(frame_rate):.2f} FPS"
    )
    output_duration = float(
        info["format"]["duration"]
    )
    duration_difference = abs(
        output_duration - expected_duration
    )
    duration_ok = (
        duration_difference <= DURATION_TOLERANCE
    )
    report(
        "Video duration",
        duration_ok,
        (
            f"{output_duration:.2f}s "
            f"(expected {expected_duration:.2f}s)"
        )
    )
    print("\nChecking file decoding...")
    decode_result = subprocess.run(
        [
            "ffmpeg",
            "-v", "error",
            "-i", str(OUTPUT_FILE),
            "-f", "null",
            "-"
        ],
        capture_output=True,
        text=True
    )
    decode_ok = decode_result.returncode == 0
    report(
        "Media decoding",
        decode_ok,
        "File decoded successfully"
        if decode_ok
        else decode_result.stderr[-1000:]
    )
    print("\n================================")
    if all(results):
        print("QC RESULT: PASS")
        print("BEAST MODE OUTPUT VERIFIED")
    else:
        print("QC RESULT: FAIL")
        print("Please inspect the failed checks.")
        raise RuntimeError(
            "Automatic Quality Control failed."
        )
    print("================================")
    return output_duration
# ==========================================
# MAIN ENGINE
# ==========================================
def main():
    check_ffmpeg()
    for directory in (
        INPUT_DIR,
        AUDIO_DIR,
        ASSETS_DIR,
        OUTPUT_DIR
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True
        )
    clips = sorted(
        (
            path for path in INPUT_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
        ),
        key=lambda path: path.name.lower()
    )
    if not clips:
        raise RuntimeError(
            "No video clips found. "
            "Add MP4 or MOV files to studio/input/"
        )
    if not MUSIC_FILE.is_file():
        raise RuntimeError(
            "Music file is missing. "
            "Add music.mp3 to studio/audio/"
        )
    print(
        f"\nFound {len(clips)} video clip(s)."
    )
    print("\nCLIP ORDER:")
    for index, clip in enumerate(clips, start=1):
        print(
            f"{index}. {clip.name}"
        )
    print("\nMusic file found.")
    print("\nCINEMATIC COLOR SETTINGS:")
    print(f"Contrast: {COLOR_CONTRAST}")
    print(f"Brightness: {COLOR_BRIGHTNESS}")
    print(f"Saturation: {COLOR_SATURATION}")
    print(f"Gamma: {COLOR_GAMMA}")
    expected_duration = sum(
        get_duration(clip)
        for clip in clips
    )
    print(
        f"\nExpected total duration: "
        f"{expected_duration:.2f} seconds"
    )
    print("\nPreparing cinematic video...")
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        normalized_clips = []
        for index, clip in enumerate(
            clips,
            start=1
        ):
            destination = (
                temp_dir / f"clip_{index:03d}.mp4"
            )
            print(
                f"\nNormalizing: {clip.name}"
            )
            normalize_clip(
                clip,
                destination
            )
            normalized_clips.append(
                destination
            )
        concat_file = temp_dir / "concat.txt"
        create_concat_file(
            normalized_clips,
            concat_file
        )
        joined_video = temp_dir / "joined.mp4"
        print("\nJoining clips...")
        run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(joined_video)
        ])
        duration = get_duration(
            joined_video
        )
        print(
            f"\nTotal video duration: {duration:.2f} seconds"
        )
        print(
            "\nMixing original audio with background music..."
        )
        render_final_video(
            joined_video,
            duration
        )
    # AUTOMATIC QUALITY CONTROL
    final_duration = quality_control(
        expected_duration
    )
    print("\n================================")
    print("BEAST MODE V1.3 RENDER COMPLETE")
    print("================================")
    print(f"Output: {OUTPUT_FILE}")
    print(
        f"Duration: {final_duration:.2f} seconds"
    )
    print("Resolution: 1080x1920")
    print("Frame rate: 30 FPS")
    print("Original audio: Preserved where available")
    print("Background music: Mixed")
    print("Cinematic color grading: Enabled")
    print(
        f"Watermark: "
        f"{'Included' if WATERMARK_FILE.exists() else 'Disabled'}"
    )
    print("Automatic Quality Control: PASS")
# ==========================================
# START ENGINE
# ==========================================
if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"\nERROR: {error}",
            file=sys.stderr
        )
        sys.exit(1)
