"""Everything that can be verified without an API key.

    python selfcheck.py

Exists because "it's set up" should be a thing you can run, not a claim.
"""
import os, sys

import vizdoom as vzd
from dotenv import load_dotenv

load_dotenv()
from doom_agent import BUTTONS, describe, heuristic, play  # noqa: E402

ok = True
def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")

check("vizdoom engine", hasattr(vzd, "DoomGame"), vzd.__version__)
check("scenario present",
      os.path.exists(os.path.join(vzd.scenarios_path, "defend_the_center.cfg")))
try:
    from typesafe_sdk import Choice, Noul, TypeSafeClient  # noqa: F401
    check("typesafe-sdk", True)
except ImportError as e:
    check("typesafe-sdk", False, str(e))
# A missing key is not a broken setup, so it must not fail the exit code --
# otherwise "is this ready?" and "do I have credentials?" give the same answer.
has_key = bool(os.environ.get("TYPESAFE_API_KEY"))
print(f"  {'PASS' if has_key else 'note'}  TYPESAFE_API_KEY  "
      f"{'set' if has_key else 'not set — heuristic/random work; --brain jev needs it'}")

# The bug that cost two zeroed baselines: bearing sign. A monster to the LEFT
# has a POSITIVE bearing, so the heuristic must turn left for it.
check("turn direction", heuristic({"monsters_nearest_first":
      [{"kind": "Demon", "distance": 200, "bearing_deg": 90}]}) == "TURN_LEFT")
check("turn direction (mirror)", heuristic({"monsters_nearest_first":
      [{"kind": "Demon", "distance": 200, "bearing_deg": -90}]}) == "TURN_RIGHT")
check("fires when aligned", heuristic({"monsters_nearest_first":
      [{"kind": "Demon", "distance": 200, "bearing_deg": 2}]}) == "ATTACK")

scores = play(heuristic, episodes=2, tics=4, quiet=True, seed=1234)
mean = sum(scores) / len(scores)
check("heuristic plays", mean > 2, f"{mean:.1f} kills (bar is ~6.5 over 20)")

print("\n" + ("setup ok" if ok else "SETUP BROKEN — see failures above")
      + (" · ready to run --brain jev" if has_key
         else " · export TYPESAFE_API_KEY to run --brain jev"))
sys.exit(0 if ok else 1)
