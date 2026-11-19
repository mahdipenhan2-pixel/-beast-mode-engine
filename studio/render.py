#!/usr/bin/env python3

import subprocess
import tempfile
from pathlib import Path
import sys

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

def run(command):
    print("Running:", " ".join(map(str, command)))
    subprocess.run(command, check=True)

def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("FFmpeg is not installed.")

def get_duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(result.stdout.strip())

def normalize_clip(source, destination):
    filters = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"fps={FPS},"
        "setsar=1"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(source),
        "-an",
        "-vf", filters,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(destination)
    ])

def main():
    check_ffmpeg()

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    clips = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in
        [".mp4", ".mov", ".m4v"]
    )

    if not clips:
        raise RuntimeError(
            "No video clips found. Add MP4 or MOV files to studio/input/"
        )

    print(f"Found {len(clips)} video clip(s).")

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        normalized = []

        for index, clip in enumerate(clips, start=1):
            output = temp_dir / f"clip_{index:03d}.mp4"
            print(f"Normalizing {clip.name}...")
            normalize_clip(clip, output)
            normalized.append(output)

        concat_file = temp_dir / "concat.txt"

        with concat_file.open("w", encoding="utf-8") as file:
            for clip in normalized:
                safe_path = str(clip).replace("\\", "/").replace("'", "'\\''")
                file.write(f"file '{safe_path}'\n")

        joined_video = temp_dir / "joined.mp4"

        run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(joined_video)
        ])

        duration = get_duration(joined_video)

        if MUSIC_FILE.exists():
            print("Adding background music...")

            fade_start = max(0, duration - 2)

            audio_filter = (
                f"atrim=0:{duration},"
                "asetpts=PTS-STARTPTS,"
                f"afade=t=out:st={fade_start}:d=2"
            )

            command = [
                "ffmpeg", "-y",
                "-i", str(joined_video),
                "-stream_loop", "-1",
                "-i", str(MUSIC_FILE),
                "-filter_complex",
                f"[1:a]{audio_filter}[audio]"
            ]

            if WATERMARK_FILE.exists():
                command += [
                    "-i", str(WATERMARK_FILE),
                    "-filter_complex",
                    (
                        f"[1:a]{audio_filter}[audio];"
                        "[0:v][2:v]overlay=W-w-45:H-h-70[video]"
                    ),
                    "-map", "[video]",
                    "-map", "[audio]"
                ]
            else:
                command += [
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
                str(OUTPUT_FILE)
            ]

            run(command)

        else:
            print("WARNING: No music.mp3 found. Rendering without audio.")

            run([
                "ffmpeg", "-y",
                "-i", str(joined_video),
                "-c", "copy",
                "-movflags", "+faststart",
                str(OUTPUT_FILE)
            ])

    print("\nRENDER COMPLETE")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Duration: {duration:.2f} seconds")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
