"""Play the same scenario yourself, scored the same way.

    python play.py

No API key, no model. Just you, the same map, the same seed, and the same
counter the bots were measured on. Mouse or arrow keys turn, Ctrl or the mouse
button fires. You cannot walk: defend_the_center gives you three buttons, which
is exactly what Jev gets.
"""
from __future__ import annotations

import argparse, os, statistics

import vizdoom as vzd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1234,
                    help="same default as the bots, so scores are comparable")
    a = ap.parse_args()

    g = vzd.DoomGame()
    g.load_config(os.path.join(vzd.scenarios_path, "defend_the_center.cfg"))
    g.set_window_visible(True)
    g.set_screen_resolution(vzd.ScreenResolution.RES_800X600)
    # SPECTATOR hands input to you; the script just watches and keeps score.
    g.set_mode(vzd.Mode.SPECTATOR)
    if a.seed >= 0:
        g.set_seed(a.seed)
    g.init()

    print(f"defend_the_center · seed {a.seed if a.seed >= 0 else 'random'} · "
          f"{a.episodes} episodes")
    print("  turn with the mouse or arrow keys, fire with Ctrl.\n")
    scores = []
    for i in range(a.episodes):
        g.new_episode()
        while not g.is_episode_finished():
            g.advance_action()
        scores.append(g.get_total_reward())
        print(f"  episode {i+1}: {scores[-1]:.0f} kills")
    g.close()

    mean = statistics.mean(scores)
    print(f"\n  YOU: {mean:.2f} kills over {len(scores)} episodes")
    print("  for reference, over 20 episodes on this seed:")
    print("    random 0.75 · hand-coded 6.55 · Jev (given the rule) 6.55 · "
          "Jev (judging for itself) -0.60")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
