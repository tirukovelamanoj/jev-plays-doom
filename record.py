"""Record Jev playing, so the demo costs nothing to watch twice.

    python record.py --out docs/jev-doom.mp4 --seconds 60

Every decision is a live API call, so a 15-minute session is ~2,000 requests.
A recording is made once and replayed forever.

Frames are captured every tic (35/s) rather than every decision, so the video
runs at true game speed instead of stuttering four frames at a time.
"""
from __future__ import annotations

import argparse, os, time

import numpy as np
import vizdoom as vzd
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()
from doom_agent import BUTTONS, describe, heuristic, JevBrain  # noqa: E402

TICS_PER_SEC = 35


def _font(size: int):
    """The PIL default font is ~11px and unreadable at 640x480."""
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


BIG, SMALL = _font(20), _font(14)


def overlay(frame: np.ndarray, label: str, pick: str, conf: float | None,
            kills: int, ms: float) -> np.ndarray:
    """Burn the decision into the frame. Without it the video is just Doom —
    the whole point is showing what the model chose and how sure it was."""
    img = Image.fromarray(frame)
    d = ImageDraw.Draw(img, "RGBA")
    w, _ = img.size
    d.rectangle([0, 0, w, 44], fill=(0, 0, 0, 175))
    d.text((12, 6), f"{label}  {pick}", fill=(120, 220, 255), font=BIG)
    if conf is not None:
        d.text((250, 4), f"confidence {conf:.2f}", fill=(200, 200, 200), font=SMALL)
        d.rectangle([250, 24, 370, 33], outline=(90, 90, 90))
        d.rectangle([250, 24, 250 + int(120 * conf), 33],
                    fill=(90, 220, 120) if conf > 0.6 else (230, 170, 60))
    d.text((w - 160, 4), f"kills {kills}", fill=(255, 210, 120), font=BIG)
    if ms > 0:
        d.text((w - 160, 28), f"{ms:.0f} ms/decision", fill=(150, 150, 150), font=SMALL)
    return np.asarray(img)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/jev-doom.mp4")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--tics", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--brain", choices=["jev", "heuristic"], default="jev")
    a = ap.parse_args()

    import imageio
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)

    g = vzd.DoomGame()
    g.load_config(os.path.join(vzd.scenarios_path, "defend_the_center.cfg"))
    g.set_window_visible(False)
    g.set_screen_resolution(vzd.ScreenResolution.RES_640X480)
    g.set_screen_format(vzd.ScreenFormat.RGB24)
    g.set_objects_info_enabled(True)
    g.set_render_hud(True)
    g.set_available_game_variables([vzd.GameVariable.HEALTH, vzd.GameVariable.AMMO2,
                                    vzd.GameVariable.POSITION_X,
                                    vzd.GameVariable.POSITION_Y, vzd.GameVariable.ANGLE])
    g.set_seed(a.seed)
    g.init()

    brain = JevBrain() if a.brain == "jev" else heuristic
    label = "JEV" if a.brain == "jev" else "HEURISTIC"
    want = int(a.seconds * TICS_PER_SEC)
    frames, calls, spent, episode = 0, 0, 0.0, 0

    writer = imageio.get_writer(a.out, fps=TICS_PER_SEC, codec="libx264",
                                quality=8, macro_block_size=None)
    try:
        while frames < want:
            g.new_episode(); episode += 1
            print(f"  episode {episode}…", flush=True)
            while not g.is_episode_finished() and frames < want:
                s = g.get_state()
                if s is None:
                    break
                t0 = time.monotonic()
                pick = brain(describe(s))
                dt = time.monotonic() - t0
                spent += dt; calls += 1
                conf = brain.confidences[-1] if hasattr(brain, "confidences") else None
                act = [1 if b == pick else 0 for b in BUTTONS]
                # one tic at a time so every rendered frame lands in the video
                for _ in range(a.tics):
                    if g.is_episode_finished() or frames >= want:
                        break
                    g.make_action(act, 1)
                    st = g.get_state()
                    if st is None or st.screen_buffer is None:
                        continue
                    writer.append_data(overlay(st.screen_buffer, label, pick, conf,
                                               int(g.get_total_reward()),
                                               spent / calls * 1000))
                    frames += 1
    finally:
        writer.close(); g.close()

    print(f"\n  wrote {a.out}  ·  {frames} frames ≈ {frames/TICS_PER_SEC:.0f}s "
          f"·  {episode} episodes  ·  {calls} API calls  ·  "
          f"{spent/max(calls,1)*1000:.0f}ms each")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
