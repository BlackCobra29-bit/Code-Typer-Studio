"""Shared high-resolution MP4 pipeline for the code and terminal studios."""
from __future__ import annotations

import math
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import imageio.v2 as imageio
import numpy as np


def mp4_render_scale(options) -> float:
    """Fit the logical scene into Full HD, keeping its layout and aspect ratio."""
    if options.width == options.height:
        return max(1.0, 1080 / options.width)
    target = (1920, 1080) if options.width > options.height else (1080, 1920)
    return max(1.0, min(target[0] / options.width, target[1] / options.height))


def encode_mp4(renderer, prefix: str, fps: int) -> bytes:
    """Render a bounded number of frames ahead while FFmpeg encodes in order."""
    if not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError("MP4 frame rate must be an integer between 1 and 120.")
    frame_count = math.ceil(renderer.duration * fps / 1000)
    workers = min(4, os.cpu_count() or 1)

    def render(time: float):
        return np.asarray(renderer.frame(time))

    with TemporaryDirectory(prefix=prefix) as directory:
        path = Path(directory) / "animation.mp4"
        with imageio.get_writer(
            str(path), fps=fps, codec="libx264", quality=None,
            macro_block_size=1, pixelformat="yuv420p",
            ffmpeg_params=[
                "-preset", "veryfast", "-crf", "10", "-threads", "2",
                "-vf", "scale=out_color_matrix=bt709,pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-color_range", "tv",
                "-movflags", "+faststart",
            ],
        ) as writer:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                pending = deque()
                next_frame = 0
                previous_key = previous_future = None

                def schedule(index):
                    nonlocal previous_key, previous_future
                    time = index * 1000 / fps
                    key = renderer.frame_key(time)
                    # Holds still contain every 60 fps sample, but reuse an
                    # identical raster. Only the last key/future is retained.
                    if previous_future is None or key != previous_key:
                        previous_future = pool.submit(render, time)
                        previous_key = key
                    pending.append(previous_future)

                for _ in range(min(frame_count, workers * 2)):
                    schedule(next_frame)
                    next_frame += 1
                while pending:
                    writer.append_data(pending.popleft().result())
                    if next_frame < frame_count:
                        schedule(next_frame)
                        next_frame += 1
        return path.read_bytes()
