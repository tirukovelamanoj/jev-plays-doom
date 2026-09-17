<div align="center">

# Doom · System One

**Doom played by a model that never sees the screen** — structured game state
in, one button out.

[![Python](https://img.shields.io/badge/python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![ViZDoom](https://img.shields.io/badge/ViZDoom-1.3-8b0000?style=flat-square)](https://vizdoom.farama.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

![Jev turning onto a target and firing](docs/turn-then-shoot.gif)

*Jev turns until the monster lines up, then fires. Its decision and confidence
are burned into every frame.*

<sub>Full minute: [`docs/jev-doom.mp4`](docs/jev-doom.mp4) · recorded once, see
[Recording](#recording)</sub>

</div>

A [System One model](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
takes unstructured state and returns a *typed* decision — no free text, no
parsing, calibrated probabilities. That is a game loop, so this plays Doom with
one.

The model is [Jev](https://docs.typesafe.ai/), TypeSafe's first System One
model, called through their Python SDK.

```
  ViZDoom (headless)                doom_agent.py              the model
 ┌──────────────────┐   objects,   ┌──────────────┐   JSON    ┌────────────┐
 │ defend_the_      ├─ positions ─►│ describe()   ├── state ─►│ Choice over│
 │ center.wad       │   health,    │  → bearings  │           │ 3 buttons  │
 │                  │◄── ammo ─────┤              │◄─"ATTACK"─┤            │
 └──────────────────┘ make_action  └──────────────┘           └────────────┘
```

**No pixels.** The model is told where the monsters are, not shown them.

## Quick start

```bash
uv sync --extra jev
.venv/bin/python selfcheck.py                      # verifies setup, no key needed
.venv/bin/python doom_agent.py --brain heuristic
```

Then for Jev — get a key at [console.typesafe.ai](https://console.typesafe.ai/)
and put it in `.env`:

```bash
cp .env.example .env        # then fill in TYPESAFE_API_KEY
.venv/bin/python doom_agent.py --brain jev --episodes 20 --quiet
```

`.env` is gitignored and loaded automatically. A real exported environment
variable still takes precedence, so CI does not need the file.

## Scores

`defend_the_center` — you stand in the middle of a circular arena with a pistol
and 26 bullets while demons close in. Score is kills before you die.

20 episodes, seed 1234, identical for every brain.

| brain | kills | spread | latency | confidence |
|---|---|---|---|---|
| random | 0.75 | −1 … 3 | — | — |
| hand-coded aim | 6.55 | 4 … 9 | 0 ms | — |
| **Jev** | **6.55** | 5 … 11 | **212 ms** | 0.88 mean |

Both scored exactly 131 kills across the 20 episodes. Per-episode they differ
(episode 16: 11 vs 9), so the identical mean is coincidence rather than the same
policy. Latency held at 212 ms over 2,642 calls — inside TypeSafe's stated
70–500 ms, measured on a laptop.

> [!WARNING]
> **That 6.55 does not show Jev can play Doom.** The `rule` criteria spell out
> the same 8° threshold the hand-coded brain uses, so the model was asked to
> evaluate a condition it was handed, not to work out the geometry. Agreement
> with the heuristic was 30/30 in a sampled episode. See below for what happens
> when the rule is removed.

### Take the rule away and it stops shooting

`--criteria intent` describes what each button is *for* and leaves the model to
judge what "lined up" means. Same seed, same state, same everything else:

| criteria | kills (10 eps) | ATTACK picks /30 | confidence |
|---|---|---|---|
| `rule` — threshold given | **6.20** | 10 | 0.88 |
| `intent` — judgment required | **−0.60** | 0 | 0.65 |

It never fires. It turns, adjusts, turns again, and dies with 26 bullets. Three
further framings, each removing an objection, did not change it:

| variant | ATTACK /30 |
|---|---|
| turns reworded so they no longer claim the aligned case | 0 |
| plus the weapon's cone stated as a fact in state | 0 |
| plus the cost of turning stated, matching the cost of firing | 1 |

So the tie was the rule doing the work. Given a numeric boundary Jev applies it
reliably and fast; asked to invent one from a bare `bearing_deg`, it will not
commit.

**Confidence caught it.** It fell from 0.88 to 0.41 as the rule was removed,
hitting 0.07 on individual calls — the model signalled that it did not know.
`--conf-floor 0.5` would have routed those decisions to the heuristic
automatically, which is the whole argument for a calibrated probability over a
bare label.

> [!NOTE]
> One scenario, one model, and criteria written by someone who is not a prompt
> specialist. A better-phrased `intent` may well close the gap; the experiment
> is a flag with both variants committed, so it is cheap to try.

> [!NOTE]
> The seed matters more than it looks. Episodes are stochastic, and the same
> brain swings 4–5 kills between episodes — wider than the gap you are likely
> measuring. An unseeded five-episode run of this heuristic gave 8.80 and then
> 6.80; neither was the model getting better or worse. Keep the seed fixed and
> the episode count up, or you are reading noise.

## What it looks like

| | |
|---|---|
| ![firing](docs/firing.jpg) | ![point blank](docs/point-blank.jpg) |
| `ATTACK` at 0.93 — two monsters closing, one lined up | `TURN_RIGHT` at 0.97 — still pivoting with a demon on top of it |

The overlay is the whole point: you can see which button it chose and how sure
it was, frame by frame. `record.py` draws it.

## What the model sees

```json
{
  "health": 100,
  "ammo": 26,
  "facing_deg": 0,
  "monsters_nearest_first": [
    {"kind": "Demon", "distance": 244, "bearing_deg": -163},
    {"kind": "Demon", "distance": 283, "bearing_deg":   90}
  ],
  "note": "bearing 0 = dead ahead. POSITIVE means LEFT, NEGATIVE means RIGHT."
}
```

And what it answers — three options, described rather than enumerated:

```python
Choice(criteria={
    "TURN_LEFT":  "rotate left — use when the target's bearing is POSITIVE",
    "TURN_RIGHT": "rotate right — use when the target's bearing is NEGATIVE",
    "ATTACK":     "fire now — only worth it when a monster is nearly straight ahead",
})
```

Cardinality 3. That is the whole reason Doom suits these models: it is a choice
among a handful of buttons, not a search over a large space.

> [!IMPORTANT]
> Doom's `ANGLE` increases **counter-clockwise**, so a positive bearing is to the
> **left**. Getting this backwards makes the agent spin in place and score zero
> — and because the same text goes into the model's state, it fails the same way
> and it looks like the model's fault. The hand-coded brain on identical state is
> what catches it.

## Two questions, one call

Independent questions run in parallel and, per TypeSafe's docs, *"adding
questions barely changes the response time"* — so a speculative one is close to
free, and code decides whether it matters:

```python
questions={
    "action":    Choice(criteria=WHAT_EACH_DOES),
    "in_danger": Noul(instructions="Is a monster close enough to hurt you "
                                   "within the next second?"),
}
```

Asking these separately would double latency per decision, which at ~10
decisions a second is the entire budget.

## Confidence is the interesting output

A Choice answer is a distribution, not a label: `choice`, `probabilities`, and a
`confidence` derived from how peaked the distribution is. Flat across three
buttons means the model has no idea, which is worth acting on rather than
discarding. `--conf-floor 0.4` hands those cases back to the geometry:

```
  confidence mean 0.87, min 0.31; 12 fell back
```

> [!NOTE]
> Typed output guarantees the interface, not the answer — TypeSafe's own docs
> say so. A confident wrong answer is the failure mode to watch for, not a
> malformed one.

## Open questions

**Can `intent` be phrased so it fires?** Answered negatively for four
phrasings, but that is not a proof. A derived field in state — *"the nearest
monster is within your firing cone: true"* — would probably do it, though that
is edging back toward handing over the answer.

**Is `in_danger` worth anything?** It rides along free in the same call but
nothing consumes it yet. Gating retreat or ammo conservation on it is the
obvious next use.

**Does confidence predict error?** It averaged 0.88 and never dropped below
0.23. If low-confidence decisions are disproportionately the wrong ones,
`--conf-floor` becomes a real safety net rather than a switch.

## Bring your own brain

Anything callable that takes the state dict and returns a button name:

```python
def my_brain(desc: dict) -> str:
    m = desc["monsters_nearest_first"]
    if not m:
        return "TURN_RIGHT"
    return "ATTACK" if abs(m[0]["bearing_deg"]) <= 8 else "TURN_LEFT"
```

## Recording

Every decision is a live API call, so a 15-minute session is roughly 2,000
requests. Record once and replay forever:

```bash
uv sync --extra jev --extra record
.venv/bin/python record.py --out docs/jev-doom.mp4 --seconds 60
```

The GIF and stills above came out of that same mp4:

```bash
FF=$(python -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())")
$FF -ss 23.4 -t 4 -i docs/jev-doom.mp4 \
    -vf "fps=10,scale=400:-1,palettegen=max_colors=64" pal.png
$FF -ss 23.4 -t 4 -i docs/jev-doom.mp4 -i pal.png \
    -lavfi "fps=10,scale=400:-1[x];[x][1:v]paletteuse" docs/turn-then-shoot.gif
```

`imageio-ffmpeg` bundles its own ffmpeg, so there is nothing to install
system-wide. Frames are captured every tic (35/s) rather than once per
decision, so the video runs at true game speed instead of stuttering four
frames at a time. `--brain heuristic` records the same way and costs nothing.

## Options

| flag | default | |
|---|---|---|
| `--brain` | `heuristic` | `heuristic`, `random`, or `llm` |
| `--episodes` | `3` | |
| `--tics` | `4` | game tics per decision — raise it for a slow model |
| `--seed` | `1234` | fixed so runs compare; `-1` randomises |
| `--jev-model` | `jev-latest` | |
| `--conf-floor` | `0.0` | below this confidence, fall back to the heuristic |

`--tics` is the fairness dial: more game time per decision, same number of
decisions. Raise it if the round trip is slower than the game.

## What is actually ours

Nothing in this repo is game code. `pip install vizdoom` ships a compiled
[ZDoom](https://zdoom.org/) engine and Freedoom's BSD-licensed assets, so the
1993 monster AI, hitscan and collision are the real thing.

```
doom_agent.py    describe() · brains · the loop     ~140 lines
vizdoom          the engine, the WADs, the physics    57 MB
```

## License

MIT — see [LICENSE](LICENSE).
