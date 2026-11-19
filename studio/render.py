#!/usr/bin/env python3
import subprocess
import tempfile
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
AUDIO_DIR = ROOT / "audio"
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "BEAST-MODE-FINAL.mp4"
MUSIC_FILE = AUDIO_DIR / "music.mp3"
WATERMARK_FILE = ASSETS_DIR / "watermark.png"
WIDTH = 1080
HEIGHT = 1920
FPS = 30
MUSIC_VOLUME = 0.22
ORIGINAL_AUDIO_VOLUME = 1.0
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
def run(command):
    print("\nRunning:", " ".join(map(str, command)))
    subprocess.run(command, check=True)
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
            raise RuntimeError(f"{executable} is not installed.")
def get_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError("Invalid video duration.")
    return duration
def has_audio(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return bool(result.stdout.strip())
def normalize_clip(source, destination):
    duration = get_duration(source)
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"fps={FPS},"
        "setsar=1"
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
            "-af", "aresample=48000,apad",
        ]
    else:
        command += [
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", video_filter,
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
def create_concat_file(clips, concat_file):
    with concat_file.open("w", encoding="utf-8") as file:
        for clip in clips:
            safe_path = str(clip).replace("\\", "/").replace("'", "'\\''")
            file.write(f"file '{safe_path}'\n")
def render_final_video(video_file, duration):
    fade_duration = min(2.0, duration)
    fade_start = max(0.0, duration - fade_duration)
    audio_filter = (
        f"[0:a]volume={ORIGINAL_AUDIO_VOLUME}[original];"
        f"[1:a]volume={MUSIC_VOLUME},"
        f"atrim=duration={duration},"
        "asetpts=PTS-STARTPTS[music];"
        "[original][music]"
        "amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
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
def main():
    check_ffmpeg()
    for directory in (
        INPUT_DIR,
        AUDIO_DIR,
        ASSETS_DIR,
        OUTPUT_DIR
    ):
        directory.mkdir(parents=True, exist_ok=True)
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
            "No video clips found. Add MP4 or MOV files to studio/input/"
        )
    if not MUSIC_FILE.is_file():
        raise RuntimeError(
            "Music file is missing. Add music.mp3 to studio/audio/"
        )
    print(f"\nFound {len(clips)} video clip(s).")
    print("Music file found.")
    print("\nCLIP ORDER:")
    for index, clip in enumerate(clips, start=1):
        print(f"{index}. {clip.name}")
    print("\nPreparing vertical video...")
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        normalized_clips = []
        for index, clip in enumerate(clips, start=1):
            destination = temp_dir / f"clip_{index:03d}.mp4"
            print(f"\nNormalizing: {clip.name}")
            normalize_clip(clip, destination)
            normalized_clips.append(destination)
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
        duration = get_duration(joined_video)
        print(f"\nVideo duration: {duration:.2f} seconds")
        print("\nMixing original audio with background music...")
        render_final_video(joined_video, duration)
    if not OUTPUT_FILE.is_file() or OUTPUT_FILE.stat().st_size == 0:
        raise RuntimeError(
            "Final video was not created correctly."
        )
    print("\n================================")
    print("BEAST MODE RENDER COMPLETE")
    print("================================")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Duration: {duration:.2f} seconds")
    print("Resolution: 1080x1920")
    print("Frame rate: 30 FPS")
    print("Original audio: Preserved")
    print(f"Music volume: {MUSIC_VOLUME}")
    print(f"Watermark: {'Included' if WATERMARK_FILE.exists() else 'Disabled'}")
if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
