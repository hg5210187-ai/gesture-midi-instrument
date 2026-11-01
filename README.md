# Gesture MIDI Instrument

An instrument you play in the air. A webcam watches both hands: the **right hand plays
notes**, the **left hand runs a looper**. The program makes no sound of its own — it sends
MIDI, so any DAW or synth plays it.

This repository is the instrument itself and the record of how it was built, from a first
keypoint prototype in March 2026 to one self-trained detector running under Core ML in
October 2026.

🛠 **[docs/BUILD_FROM_SCRATCH.md](docs/BUILD_FROM_SCRATCH.md)** — the build, stage by stage:
what was added, why, what went wrong, and the order to build it in if you start from zero.

🧩 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — modules, threads, the contract between
vision and logic, the MIDI that leaves the program, and every tunable constant.

🧪 **[docs/MODEL_PROCEDURES.md](docs/MODEL_PROCEDURES.md)** — every detector trained for the
instrument, in the order it was made, with the procedure that produced it.

📦 **[docs/MODELS.md](docs/MODELS.md)** — which model file each program needs and how to
download it. The trained weights are in the
[`models-v1` release](../../releases/tag/models-v1).

🔬 **[midi-gesture-research](https://github.com/hg5210187-ai/midi-gesture-research)** — the
companion study that chose the detector: 114 training runs, accuracy by cross-validation,
latency measured on the laptop the instrument runs on.

---

> ### ⭐ Preferred model: `hbb-s-fold1-320`
>
> The research compared 38 model configurations over 114 training runs. The one it chose is
> **YOLO26-s with plain boxes at 320 px, run under Core ML**: the most accurate model that
> holds a 10 ms budget on a MacBook Air M4 for 15 continuous minutes (7.93 ms median,
> 0.8056 ± 0.0437 mAP50-95). `main_obb.py` runs it.
>
> [Why it was chosen](https://github.com/hg5210187-ai/midi-gesture-research/blob/main/REPORT.md#9-the-deployment-choice)
> · [How it was made](docs/MODEL_PROCEDURES.md#7--the-research-study-and-hbb-s-fold1-320)
> · [Download](docs/MODELS.md#download)

## How you play it

| Hand | Movement | Result |
|---|---|---|
| Right | Up / down | Pitch: the notes of the selected scale, or a continuous glide in Theremin mode |
| Right | Toward / away from the camera | Volume (MIDI CC 7), from the size of the hand's box |
| Right | Pull back or leave the frame | Note off: below the volume gate the note is released, not just made quiet |
| Left | Hold a fist | Looper: idle → recording → playing → idle. In the two Cubase programs: fist = record → play, fist kept 2 s = record the next track over the playing loops, thumb out = stop |

The picture is mirrored. A hand on the right half of it is the right hand; a hand on the left
half is the left hand. In the rotation instrument (`main_rotate.py`) pitch comes from the
right hand's **tilt angle** instead of its height.

The video shows what the instrument is reading: a box on each hand, the line where pitch is
sampled, the band of the note being played with its name and frequency (`A4 (440 Hz)`), and
the looper state.

## The programs

Each stage of the build left a program that still runs. They share the MIDI engine, looper,
scales, UI and overlay, and differ in how they see the hands.

| Program | Detector | Model file | What it is |
|---|---|---|---|
| ⭐ `main_obb.py` | YOLO26-s detect, 3 gesture classes | `hbb-s-fold1-320.mlpackage` or `.pt` | **The current version and the one to use.** One model for both hands, Core ML, lowest latency |
| `main_cubase.py` | same as `main_obb.py` | same as `main_obb.py` | `main_obb.py` made for Cubase: the fist records loops in Cubase, the app switches Cubase tracks, the Instrument menu switches HALion Sonic sounds. See [Cubase version](#cubase-version) |
| `main_cubase_lite.py` | same as `main_obb.py` | same as `main_obb.py` | `main_cubase.py` with a small, fast window: camera picture, Scale, Root Note, 1 / 2 octaves, Calibrate. For playing and filming. `--model x` or `--model v8` swaps the detector. See [Light version](#light-version) |
| `main_rotate.py` | YOLO26 OBB, 3 gesture classes | `YOLO26<size>-MIDI.pt` | Pitch from rotating the hand. Five model sizes, `--model n\|s\|m\|l\|x` |
| `main.py` | YOLOv8n hand-pose, 21 keypoints | `yolov8n-hand-pose.pt` | The first working version. Right hand from its box, left-hand fist from keypoints |
| `main_mediapipe.py` | MediaPipe HandLandmarker | `hand_landmarker.task` (public download) | Needs no trained weights. Added because the YOLO hand-pose model fired on faces and curtains |

`main_obb.py` keeps the name of the oriented-box experiment it started as. It now runs the
axis-aligned model chosen by the research study.

## Quick start (macOS)

Developed on a MacBook Air M4. It needs a webcam, Python 3.12 with Tk,
[uv](https://docs.astral.sh/uv/), and the [GitHub CLI](https://cli.github.com/) to fetch the
models.

Clone this repository, then from inside it:

```bash
brew install python@3.12 python-tk@3.12 uv gh
uv sync
uv run python tests/check_headless.py     # ends with ALL PASS; needs no camera or MIDI port
```

`pyproject.toml` tells uv to use the system (Homebrew) Python, because the UI needs Tk and
`python-tk@3.12` provides it.

1. **Turn on a MIDI bus.** Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver →
   tick "Device is online". If no IAC port exists, the app creates a virtual port named
   `Indigo Gesture Controller` instead.
2. **Open something that plays MIDI** from the IAC bus: a DAW instrument track, or any
   General MIDI synth.
3. **Get the preferred model** from the [`models-v1` release](../../releases/tag/models-v1):
   ```bash
   gh release download models-v1 --pattern 'hbb-s-fold1-320.*'
   unzip hbb-s-fold1-320.mlpackage.zip && rm hbb-s-fold1-320.mlpackage.zip
   ```
   Or download the two files from the release page in a browser and put them in this folder.
4. **Run it.** macOS asks once for camera permission.
   ```bash
   uv run python main_obb.py
   ```
5. Hold your right hand far from the camera, press **Calibrate Min**, then move it closer.
   That sets the size that means silence.

### The other programs

```bash
# Rotation instrument: pitch from tilting the hand
gh release download models-v1 --pattern 'YOLO26s-MIDI.pt'
uv run python main_rotate.py --model s

# MediaPipe: needs only a public download from Google (7.8 MB)
curl -L -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
uv run python main_mediapipe.py

# YOLOv8 hand-pose: needs yolov8n-hand-pose.pt, which is not distributed here
uv run python main.py
```

Every model file goes in the project root. [docs/MODELS.md](docs/MODELS.md) lists them all.

## Settings panel

| Control | What it does |
|---|---|
| Scale Type | Chromatic, Major, Minor, the seven modes, Major / Minor Pentatonic, or Theremin (continuous pitch bend around C4) |
| Root Note | C through B |
| Instrument | 33 General MIDI sounds, sent as a Program Change |
| Pitch Range | Full (5 octaves starting in octave 2), Melody (2 or 1 octaves starting in octave 4), Bass (1 octave starting in octave 2) |
| Calibrate Min | Captures the current right-hand size as volume 0 |
| Volume Sensitivity | How much the hand must grow to reach full volume (0.5–8.0, default 2.0) |
| Volume Gate | Below this volume the note is cut (0–40, default 8) |
| Show Note Borderlines | Draws every pitch band of the scale on the video |
| Show Current Pitch | Draws the sampling line, the active band and the note readout |
| Rotation Mode, Set Low / High Note | Rotation instrument only: snap to the scale or glide, and fit the pitch range to how far you rotate |

`F11` toggles fullscreen, `Esc` leaves it. The settings sidebar can be hidden.

## DAW setup

The app sends to the first port whose name contains `IAC`. Live playing is on MIDI channel 1
and the looper plays back on channel 2.

For Cubase:

- Studio → Studio Setup → Audio System: a wired output (not Bluetooth), buffer 64–128
  samples, "Release Driver when Application is in Background" **off**.
- Studio Setup → MIDI Port Setup: `IAC Driver Bus 1` ticked under "In 'All MIDI Inputs'".
  Do not route any track's MIDI output back to the IAC bus (feedback loop).
- Add an Instrument Track (for example HALion Sonic) with input `All MIDI Inputs` and
  monitoring on. With the track's MIDI channel set to `1`, live and looped notes share one
  sound; set to `Any`, the looper's channel 2 needs a sound loaded in the instrument's
  second slot.

GarageBand also receives the notes, but it ignores Program Change, so the Instrument menu
does nothing there. Quit GarageBand when using another DAW: it listens to the same bus and
would play too.

## Cubase version

`main_cubase.py` is the instrument made for Cubase LE / AI / Elements 13. It plays like
`main_obb.py`, with three differences:

- **The left hand records layered loops in Cubase.** Fist: select the start track (track 1
  unless chosen in the Cubase Track menu), cycle off, jump to the left locator, record. Fist
  again: right locator to the playhead, record off, and 0.2 s later cycle on and back to the
  left locator, so the first recording loops at exactly its own length. A fist kept 2 s while
  it plays: select the next track, cycle on, back to the left locator and record, so the new
  part lies on top of the first with the same length; recording stops by itself after one
  pass. Thumb out: stop.
  Each loop is a MIDI part on its track.
- **Cubase Track** (where the Number of Tracks slider was) selects which of the first 8
  instrument, sampler or MIDI tracks the right hand plays, in MixConsole order.
- **Instrument** sends Program Change on channel 1 to the selected track. HALion Sonic
  follows it with GM Mode on.

Volume (CC 7) is sent only when it changes, so recordings are not flooded with it.

It uses two IAC buses: notes on `IAC Driver Bus 1`, control messages on `IAC Driver Bus 2`.
A MIDI Remote script turns the control messages into Cubase actions.

One-time setup:

1. **Add Bus 2.** Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver → under Ports,
   `+`, so there is a `Bus 2`; keep "Device is online" ticked.
2. **Install the MIDI Remote script**, then start (or restart) Cubase:
   ```bash
   mkdir -p ~/Documents/Steinberg/"Cubase LE AI Elements"/"MIDI Remote"/"Driver Scripts"/Local
   cp -R cubase/midi_remote/indigo ~/Documents/Steinberg/"Cubase LE AI Elements"/"MIDI Remote"/"Driver Scripts"/Local/
   ```
   The MIDI Remote tab (lower zone) should show *Indigo GestureInstrument*. If it does not,
   use "+ Add MIDI Controller Surface", pick Indigo → GestureInstrument and set its input to
   `IAC Driver Bus 2`. Studio → MIDI Remote Manager should list it once, Connected, with
   five transport buttons and eight track buttons, none marked "Missing". After copying a changed script, press
   the reload button (↻) there.
3. **Studio → Studio Setup → MIDI Port Setup.** `IAC Driver Bus 1` ticked under "In 'All MIDI
   Inputs'"; `IAC Driver Bus 2` **not** ticked, or the control messages are recorded as data.
   Do not set any track's MIDI output to an IAC bus: it would feed back into Cubase.
4. **Preferences.** Editing → Project & MixConsole → "Enable Record on Selected MIDI Track"
   on, and MIDI → "MIDI Thru Active" on. The selected track then hears the right hand.
5. **Tracks.** Instrument tracks with input `All MIDI Inputs`, MIDI channel `1`, and
   **Monitor off** (with Monitor on, every such track would play the right hand at once). On
   a HALion Sonic track, turn on Options → GM Mode so the Instrument menu works.
6. **Loop start.** Put the left locator where loops should start; the first recording sets
   the right locator. Set the MIDI cycle-record mode to Keep Last (each layer stops just after
   one pass, and Keep Last drops the unfinished second pass), turn Auto
   Quantize off, and keep the loop area empty on other tracks. The app assumes Cubase's
   count-in is off (the metronome click can be on); with a count-in, set
   `CUBASE_COUNT_IN_BARS` and `CUBASE_TEMPO` (below).

Then:

```bash
uv run python main_cubase.py
```

If `IAC Driver Bus 2` is missing, the program still plays notes and says so at startup; the
fist and the Cubase Track menu then do nothing. Messages, all on MIDI channel 16 of Bus 2:

| CC | Cubase action | Values |
|---|---|---|
| 102 | Record | 127 on, 0 off |
| 103 | Cycle | 127 on, 0 off |
| 104 | Stop | 127 presses |
| 105 | To Left Locator | 127 presses |
| 106 | Set Right Locator (to the playhead) | 127 presses |
| 110–117 | Select track 1–8 | 127 selects |

To check the script, open MIDI Remote → Scripting Tools: Open Console. Each message received
is printed there as `Indigo <name> = <value>`.

### Light version

```bash
uv run python main_cubase_lite.py
```

`--model x` runs the same window with the heaviest gesture model, `hbb-x-fold0-416` (YOLO26-x,
416 px): the most accurate YOLO26 model on the study's test photos, about 24 ms per frame
instead of 7. `--model v8` runs it with the first version's YOLOv8n hand-pose model, exported
to Core ML, and `main.py`'s keypoint gesture logic (33 ms per frame). The full demo setup, with the environment it runs on:
[docs/CUBASE_LITE_DEMO.md](docs/CUBASE_LITE_DEMO.md).

The same instrument and the same Cubase setup, in a small window made for playing and filming:

- The camera picture at the camera's own size (640×480), and four controls: **Scale** and
  **Root Note** (starting on D minor), **Range** (1 or 2 octaves) and **Calibrate**.
- Each range ends on the root an octave or two up: D4–D5 (8 notes) or D4–D6 (15 notes) in
  D minor. The full window's ranges stop one step below it (D4–C5).
- Volume sensitivity, volume gate and the overlay use the full window's defaults.
- No Instrument or Cubase Track menu, and no Program Change is sent. Load the sound on the
  Cubase track, and click a track in Cubase to play it ("Enable Record on Selected MIDI
  Track" arms it). Switch tracks with the right hand out of view, so no note is held.
- The left fist records, plays and stops loops in Cubase as above.

Calibrate before each take: hold the right hand where it should be silent (farthest from the
camera) and press Calibrate. Without it, the place the hand first appears becomes the silent point.

Why it exists: the full window enlarges every frame to fill the screen. On a maximised window
that took 95 ms per redraw, redrawn every 40 ms, so its menus stopped responding and the
gesture model's time per frame went from 10 ms to 19 ms on average, with stalls up to 210 ms.
The light window draws in about 29 ms and leaves the model at 9 ms (measured 2026-10-29 with
the Core ML model and a synthetic frame). Cubase adds its own output latency on top: Studio →
Studio Setup → the audio device shows it, and a smaller buffer in its Control Panel lowers it.

## Environment variables

| Variable | Program | Effect |
|---|---|---|
| `MIDI_PORT=<name>` | all but the two Cubase programs | Send to the output whose name contains this text |
| `CUBASE_NOTES_PORT=<name>`, `CUBASE_CONTROL_PORT=<name>` | `main_cubase.py`, `main_cubase_lite.py` | Exact names of the notes and control outputs (default `IAC Driver Bus 1`, `IAC Driver Bus 2`) |
| `CAMERA_INDEX=<n>`, `CAMERA_FPS=<fps>` | `main_obb.py`, both Cubase programs | Pick another camera, request a frame rate |
| `HBB_MODEL=<file>`, `HBB_IMGSZ=<px>`, `HBB_DEVICE=mps\|cpu` | `main_obb.py`, both Cubase programs | Gesture model, input size, PyTorch device |
| `CUBASE_TEMPO=<bpm>`, `CUBASE_COUNT_IN_BARS=<n>`, `CUBASE_COUNT_IN_BEATS=<n>` | both Cubase programs | Cubase's count-in, if it is on (default 0 bars = off; 4 beats per bar; tempo default 120). A held note is re-sent after it |
| `MIDI_LATENCY_DEBUG=1` | `main_obb.py`, both Cubase programs | Print loop rate, inference time and frame age at MIDI send every 5 s |
| `OBB_DEBUG=1` | `main_obb.py`, both Cubase programs | Print every detection (class, confidence, area, centre) |
| `HAND_DEBUG=1` | `main.py`, `main_mediapipe.py` | Print every raw detection before filtering |
| `ROT_DEBUG=1` | `main_rotate.py` | Print angle, note, bend and volume per frame |

## Measured

On the MacBook Air M4 with its built-in camera, `main_obb.py` running the Core ML model:

| | |
|---|---|
| Loop rate | 30 fps (the camera's rate) |
| Inference in the running app | 6–7.6 ms mean |
| Camera frame delivered → MIDI sent | 8–9.6 ms mean |
| Occasional single-frame spikes | 50–120 ms |

These exclude the camera's own internal delay and the DAW's audio buffer. The camera delivers
a new frame every 33.3 ms, and that interval, not the model, bounds how fast the instrument
can respond. How the loop got from about 56 ms to under 10 ms is in
[docs/BUILD_FROM_SCRATCH.md](docs/BUILD_FROM_SCRATCH.md#stage-11--cut-the-latency).

## Repository layout

```
main_mediapipe.py   main.py   main_rotate.py   main_obb.py     the four programs
main_cubase.py      main_obb.py made for Cubase
main_cubase_lite.py main_cubase.py with the light window

src/
  midi_engine.py        MIDI output: notes, CC, pitch bend, program change
  cubase_control.py     the fist and track menu as Cubase control messages (main_cubase.py)
  scales.py             scale generator, note names, frequencies
  looper.py             records and loops MIDI on its own channel
  ui.py                 settings panel and video window (CustomTkinter)
  ui_lite.py            the light window: camera picture, scale, root, calibrate
  overlay.py            what is drawn on the video
  logic.py              gestures → MIDI for the keypoint detectors
  logic_obb.py          gestures → MIDI for the gesture-class detector
  logic_rotate.py       rotation → MIDI
  vision_mediapipe.py   camera + MediaPipe
  vision_ultralytics.py camera + YOLOv8 hand-pose
  vision_yolo26.py      camera + YOLO26 OBB
  vision_hbb.py         camera + YOLO26 detect (PyTorch or Core ML)
  vision_obb.py         latest-frame camera thread; the earlier two-model backend
  vision.py             the original MediaPipe backend, kept for reference

run_benchmark.py  experiment_*.py  task_engine.py  run_dry_run.py
                        playability benchmark: 3 pitch sensitivities × 4 scale types
tests/check_headless.py feeds synthetic detections through all three logic modules
cubase/midi_remote/     the Cubase MIDI Remote script for main_cubase.py
YOLO26<size>-ver        provenance of each rotation model (training date, mAP, speed)
docs/                   build record, architecture, model procedures, models
```

## Limits

- **macOS.** MIDI goes through the IAC Driver or a CoreMIDI virtual port, and the fast path
  is Core ML. Nothing else was tried.
- **One person's hands.** The self-trained models were trained on one person's hands. The
  research repository reads its accuracy figures as an upper bound for anyone else.
- **Left and right are decided by which half of the picture a hand is in**, not by true
  handedness. A left hand that crosses the middle is read as the right hand.
- **Thresholds are inherited.** `min_confidence` 0.6 and `max_box_area` 0.30 in
  `src/logic_obb.py` were tuned for an earlier model.
- **`src/vision.py` does not run** with the pinned MediaPipe 0.10.32, which no longer ships
  the legacy `mediapipe.solutions` API. `src/vision_mediapipe.py` is its replacement.

## License

The code in this repository is under GPL-3.0, see [LICENSE](LICENSE). It depends on
Ultralytics (AGPL-3.0) and MediaPipe (Apache-2.0), which keep their own licenses.
