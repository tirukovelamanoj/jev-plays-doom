"""Doom, played by a System One model, the same shape as TypeSafe's demo.

    python doom_agent.py --brain heuristic          # no API key needed
    python doom_agent.py --brain jev                # needs TYPESAFE_API_KEY

The model never sees pixels. It gets a text description of the world and
returns one of three buttons.
"""
from __future__ import annotations

import argparse, math, os, random, time

import vizdoom as vzd
from dotenv import load_dotenv

# Read .env before anything touches os.environ, so TYPESAFE_API_KEY can live in
# a file instead of being exported into every shell. A real environment
# variable still wins -- load_dotenv does not override what is already set.
load_dotenv()

BUTTONS = ["TURN_LEFT", "TURN_RIGHT", "ATTACK"]
# Two ways to describe the same three buttons, kept side by side because the
# difference between them is the actual experiment.
#
# RULE spells out the 8-degree threshold the hand-coded brain uses, so the model
# is asked to evaluate a condition it was handed. INTENT describes what each
# button is FOR and leaves the model to decide what "lined up" means. Only the
# second measures judgment; the first measures instruction-following.
CRITERIA_RULE = {
    "ATTACK": "Fire. Correct whenever the nearest monster's bearing is between "
              "-8 and +8, i.e. already lined up. Firing is how you score; do it "
              "the moment you are aligned rather than adjusting further.",
    "TURN_LEFT": "Rotate left. Correct only when the nearest monster's bearing is "
                 "GREATER than +8. Do not pick this if the bearing is between -8 "
                 "and +8; fire instead.",
    "TURN_RIGHT": "Rotate right. Correct only when the nearest monster's bearing "
                  "is LESS than -8. Do not pick this if the bearing is between -8 "
                  "and +8; fire instead.",
}

CRITERIA_INTENT = {
    "ATTACK": "Fire your weapon down your line of sight. This is the only way to "
              "score, but a shot that is not lined up hits nothing and wastes a "
              "bullet you cannot spare.",
    "TURN_LEFT": "Rotate left. This swings your line of sight toward monsters that "
                 "are to your left, and away from ones on your right.",
    "TURN_RIGHT": "Rotate right. This swings your line of sight toward monsters "
                  "that are to your right, and away from ones on your left.",
}
CRITERIA = {"rule": CRITERIA_RULE, "intent": CRITERIA_INTENT}


def describe(state) -> dict:
    """The whole game as text. This is the 'unstructured state' input."""
    hp, ammo, px, py, ang = state.game_variables
    me = None
    monsters = []
    for o in state.objects:
        if o.name == "DoomPlayer":
            me = o; continue
        # MarineChainsawVzd is decoration standing around the arena, not a
        # threat. Leaving it in made both brains aim at furniture.
        if o.name in ("Demon", "Cacodemon", "ZombieMan", "ShotgunGuy", "HellKnight",
                      "Imp", "Revenant"):
            dx, dy = o.position_x - px, o.position_y - py
            dist = math.hypot(dx, dy)
            # bearing relative to where the player is facing: 0 = dead ahead,
            # negative = to the left. This is the number the decision turns on.
            bearing = (math.degrees(math.atan2(dy, dx)) - ang + 540) % 360 - 180
            monsters.append({"kind": o.name, "distance": round(dist),
                             "bearing_deg": round(bearing)})
    # Nearest by DISTANCE, not by bearing: sorting on bearing made the target
    # flip between monsters on either side as the player turned, so it spun in
    # place instead of converging on anything.
    monsters.sort(key=lambda m: m["distance"])
    return {
        "health": int(hp), "ammo": int(ammo),
        "facing_deg": round(ang),
        "monsters_nearest_first": monsters[:6],
        "note": "bearing 0 = dead ahead. POSITIVE bearing means the monster is to "
                "your LEFT (turn left to face it); NEGATIVE means to your RIGHT.",
    }


def heuristic(desc: dict) -> str:
    """A bar to beat, so the model's score means something."""
    ms = desc["monsters_nearest_first"]
    if not ms:
        return "TURN_RIGHT"
    b = ms[0]["bearing_deg"]
    if abs(b) <= 8:
        return "ATTACK"
    return "TURN_LEFT" if b > 0 else "TURN_RIGHT"


class JevBrain:
    """The real System One model.

    Two things the docs are emphatic about, and both matter here:

    - Ask independent questions in ONE call. They run in parallel and barely
      change response time, so `retreat` rides along for free and code decides
      whether it is relevant. Asking it separately would double the latency.
    - The answer is a distribution, not a label. `confidence` says how peaked
      it is, and a flat distribution over three buttons is the model saying it
      has no idea -- which is worth acting on rather than discarding.
    """

    def __init__(self, model: str = "jev-latest", conf_floor: float = 0.0,
                 criteria: str = "rule"):
        from typesafe_sdk import TypeSafeClient
        self.client = TypeSafeClient(model=model)
        self.conf_floor = conf_floor
        self.criteria = CRITERIA[criteria]
        self.confidences: list[float] = []
        self.low_conf = 0

    def __call__(self, desc: dict) -> str:
        from typesafe_sdk import Choice, Noul
        r = self.client.system_one(
            state=desc,
            questions={
                "action": Choice(
                    instructions="You are fighting for your life in Doom, surrounded "
                                 "by monsters. Pick the single best button to press "
                                 "right now.",
                    criteria=self.criteria,
                ),
                # speculative: free to ask, and code decides if it matters
                "in_danger": Noul(instructions="Is a monster close enough to hurt you "
                                               "within the next second?"),
            },
        )
        a = r.choices["action"]
        self.confidences.append(a.confidence)
        # When the model cannot separate the options, trust the geometry instead
        # of a coin flip. Typed output guarantees the interface, not the answer.
        if a.confidence < self.conf_floor:
            self.low_conf += 1
            return heuristic(desc)
        return str(a.choice)


def play(brain, episodes: int, tics: int, quiet: bool, seed: int | None) -> list[float]:
    g = vzd.DoomGame()
    g.load_config(os.path.join(vzd.scenarios_path, "defend_the_center.cfg"))
    g.set_window_visible(False)
    g.set_objects_info_enabled(True)
    g.set_available_game_variables([vzd.GameVariable.HEALTH, vzd.GameVariable.AMMO2,
                                    vzd.GameVariable.POSITION_X, vzd.GameVariable.POSITION_Y,
                                    vzd.GameVariable.ANGLE])
    # Episodes are stochastic. Without a fixed seed two runs of the SAME brain
    # differ by more than the gap between brains, so any comparison is noise.
    if seed is not None:
        g.set_seed(seed)
    g.init()
    scores, calls, spent = [], 0, 0.0
    for ep in range(episodes):
        g.new_episode()
        while not g.is_episode_finished():
            s = g.get_state()
            if s is None:
                break
            t0 = time.monotonic()
            pick = brain(describe(s))
            spent += time.monotonic() - t0; calls += 1
            act = [1 if b == pick else 0 for b in BUTTONS]
            g.make_action(act, tics)
        scores.append(g.get_total_reward())
        if not quiet:
            print(f"  episode {ep+1}: {scores[-1]:.0f} kills")
    g.close()
    if calls:
        print(f"\n  {calls} decisions, {spent/calls*1000:.0f}ms each")
    cs = getattr(brain, "confidences", None)
    if cs:
        print(f"  confidence mean {sum(cs)/len(cs):.2f}, "
              f"min {min(cs):.2f}; {getattr(brain, 'low_conf', 0)} fell back")
    return scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", choices=["heuristic", "random", "jev"],
                    default="heuristic")
    ap.add_argument("--jev-model", default="jev-latest")
    ap.add_argument("--conf-floor", type=float, default=0.0,
                    help="below this confidence, fall back to the heuristic")
    ap.add_argument("--criteria", choices=["rule", "intent"], default="rule",
                    help="rule: hand the model the 8-degree threshold. "
                         "intent: describe what each button is for and let it judge.")
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--tics", type=int, default=4, help="game tics per decision")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--seed", type=int, default=1234,
                    help="fixed so runs are comparable; pass -1 to randomise")
    a = ap.parse_args()

    if a.brain == "heuristic":
        brain = heuristic
    elif a.brain == "random":
        brain = lambda d: random.choice(BUTTONS)          # noqa: E731
    else:
        brain = JevBrain(a.jev_model, a.conf_floor, a.criteria)

    seed = None if a.seed < 0 else a.seed
    tag = f" · criteria={a.criteria}" if a.brain == "jev" else ""
    print(f"defend_the_center · brain={a.brain}{tag} · {a.episodes} episodes · seed {seed}")
    scores = play(brain, a.episodes, a.tics, a.quiet, seed)
    mean = sum(scores) / len(scores)
    spread = max(scores) - min(scores)
    print(f"  MEAN {mean:.2f} kills over {len(scores)} episodes "
          f"(min {min(scores):.0f}, max {max(scores):.0f}, spread {spread:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
