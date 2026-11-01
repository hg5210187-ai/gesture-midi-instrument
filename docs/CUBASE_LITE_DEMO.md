# Cubase light version: demo setup

`main_cubase_lite.py` is the gesture instrument in the form used for the demo video. You play
it with your hands in front of the Mac's camera, and Cubase makes the sound. The right hand
plays the notes. The left hand records loops in Cubase, one track after another, layered over
each other, and stops them.

This page describes that one setup as of 2026-10-30: what you see, what it runs on, how to set
it up and how to record a take. The other versions are summarised briefly at the end.

```bash
cd ~/Documents/gesture-midi-instrument
uv run python main_cubase_lite.py              # standard model
uv run python main_cubase_lite.py --model x    # the heaviest, most accurate model
uv run python main_cubase_lite.py --model v8   # the first version's YOLOv8 hand-pose model
```

Everything except the gesture model is the same in all three (see [Models](#models)).

## How you play it

| Hand | Movement | Result |
|---|---|---|
| Right | Up / down | Pitch: the notes of the chosen scale, low at the bottom, high at the top |
| Right | Toward / away from the camera | Volume: the bigger the hand looks, the louder |
| Right | Pull back or leave the picture | The note stops |
| Left | Fist (about 1/6 s) | Cubase: record → play the loop |
| Left | Keep the fist 2 s while a loop plays | Record a new loop on the next track |
| Left | Thumb out (about 1/4 s) | Stop |

The picture is mirrored, so it reads like a mirror. A hand on the right half of the picture
counts as the right hand, and one on the left half as the left hand.

The left hand builds up layers, one track at a time:

1. **Fist:** Cubase selects track 1, turns cycle off, jumps to the left locator and starts
   recording. (With Cubase's count-in on, it would first click one bar, then record from
   the left locator; notes played during the clicks would not be recorded.) Play your phrase;
   there is no length limit.
2. **Fist:** this sets the loop. Cubase puts the right locator where the playhead is and stops
   recording; 0.2 s later it turns cycle on and jumps back to the left locator, so what you
   just played loops, exactly as long as you played it.
3. **Fist kept for 2 seconds:** Cubase selects the next track, jumps back to the start of the
   loop and, 0.15 s later (once it is there), records, so the new part lies exactly on top of the first one and has the
   same length. The earlier loops play again from the start with it. **Recording stops by
   itself just after one pass of the loop** (about 0.45 s into the next pass). With Cubase's
   MIDI cycle record mode on **Keep Last**, Cubase keeps the one complete pass, right up to
   the loop end, and throws away the unfinished second one, so there is no gap and nothing
   recorded twice. A short fist does nothing here, so a playing loop is
   not stopped by accident.
4. The new loop then plays with the others. A fist during its recording stops it sooner.
   Step 3 repeats for track 3, 4 and so on, up to track 8.
5. **Thumb out:** Cubase stops. The next fist starts again on track 1, and its recording sets
   a new loop length.

A note you are already holding when recording starts is sent again 0.15 s later, so Cubase
records it (Cubase only records notes that start while it records). It therefore begins
0.15 s into the recording.

Each loop becomes a MIDI part on its track. The loop length is the time between the first two
fists, to the millisecond, not rounded to bars, so Cubase's metronome and bar lines only line
up with it if you close the loop on a bar line. "Track 1, 2, 3 …" are the instrument, sampler and MIDI tracks
from the top of the project, skipping audio and group tracks. The badge on the picture shows
the track, for example `CUBASE T2: RECORDING`.

The thumb needs a little longer than the fist because the model sometimes reads a fist as a
thumb, or the other way round. With `--model v8` the fist is confirmed after 3 frames instead
of 5, as in `main.py`.

## The window

The window has a small column of controls next to the camera picture.

| Control | What it does |
|---|---|
| Scale | Chromatic, Major, Minor, the seven modes, Major / Minor Pentatonic, Theremin (continuous glide). Starts on **Minor** |
| Root Note | C to B. Starts on **D** |
| Range | **1 octave** or **2 octaves**, starting at the root in octave 4. Both end on the root, so D minor is D4–D5 (8 notes) or D4–D6 (15 notes). Starts on 2 octaves |
| Calibrate | Takes the right hand's current size as silence |
| Cubase: Idle / Recording / Playing, on track N | What the left hand last told Cubase to do, and which track the loop is on |
| Model, Detection | Which gesture model is running, and its average time per frame, updated every second. The window title names the model too |

The picture shows what the instrument reads:

- a box on each hand;
- the line where pitch is read;
- the band of the note being played, with its name and frequency;
- a `CUBASE: IDLE / RECORDING / PLAYING` badge.

Fixed in this version:

- volume sensitivity 2.0;
- the volume gate at 8, so a note below that volume is stopped rather than played very
  quietly;
- the pitch readout shown and the note borderlines hidden.

The app sends no instrument changes. The sound is whatever you load on the Cubase track.

## Environment

### Hardware

| | |
|---|---|
| Computer | MacBook Air (Mac16,12), Apple M4, 16 GB |
| Camera | The built-in MacBook Air Camera (`CAMERA_INDEX=0`), read at 640×480 |
| Sound | Cubase's Built-in Audio driver. Output latency was 14.0 ms on 2026-10-29 (see [Audio](#audio)). Use wired headphones or speakers, not Bluetooth |

### Software

| | Version |
|---|---|
| macOS | 15.5 (24F74) |
| Cubase LE AI Elements 13 | 13.0.55.328 |
| HALion Sonic | 7.1.0 |
| Groove Agent SE | 5.2.10 |
| Kontakt 8 | 8.5.1 |
| MIDI between the app and Cubase | macOS IAC Driver: `IAC Driver Bus 1` (notes), `IAC Driver Bus 2` (control) |
| Cubase MIDI Remote script | `Indigo GestureInstrument` (`cubase/midi_remote/indigo/gestureinstrument/`) |
| Python | 3.12.13 (Homebrew `python@3.12` with `python-tk@3.12` 3.12.13) |
| uv | 0.9.26 |
| GitHub CLI (only to download the model) | 2.97.0 |

### Python packages (`uv sync` installs them)

| Package | Version | Used for |
|---|---|---|
| ultralytics | 8.4.7 | running the gesture model |
| coremltools | 9.0 | the Core ML model |
| torch / torchvision | 2.9.1 / 0.24.1 | required by ultralytics |
| opencv-python | 4.13.0.90 | the camera and drawing on the picture |
| mido / python-rtmidi | 1.3.3 / 1.5.8 | MIDI output |
| customtkinter | 5.2.2 | the window |
| numpy / pillow | 2.3.5 / 12.1.0 | image handling |

Starting the app prints a warning that Torch 2.9.1 has not been tested with coremltools, and a
`SyntaxWarning` from inside coremltools. Neither affects the instrument.

### Models

Three Core ML models in the project folder, chosen with `--model`. None is stored in git.

| `--model` | File | Detector | Size | Test photos (mAP50-95) | Time per frame |
|---|---|---|---|---|---|
| `s` (default) | `hbb-s-fold1-320.mlpackage` | YOLO26-s, 320 px, 3 gesture classes | 18 MB | 0.73 | 7 ms |
| `x` | `hbb-x-fold0-416.mlpackage` | YOLO26-x, 416 px, 3 gesture classes | 106 MB | 0.82 | 24 ms |
| `v8` | `yolov8n-hand-pose.mlpackage` | YOLOv8n hand-pose, 384 px, 21 points per hand | 6.6 MB | — | 33 ms |

`s` and `x` detect the three gestures (`thumbout`, `openhand`, `closedhand`) directly. Both
come from the research study's cross-validation: for each, the fold with the best validation
score.

`v8` is the model of the first working version, `main.py`. It finds hands and 21 points on
each, and `src/logic.py` reads the gestures from the points:
- **fist:** the four fingertips near the palm;
- **thumb out:** a fist with the thumb tip more than one hand size (wrist to middle knuckle)
  from the palm. On the study's 120 labelled hands this read 24 of 33 thumbs-out as thumb
  out, and 3 of 38 fists and none of 40 open hands;
- the model also fires on still background objects such as a picture frame, so the logic
  mutes any box that stays perfectly still. Here that takes 3 s instead of the 1.5 s of
  `main.py`, so that a fist held still for 2 s still counts.

It is a third-party checkpoint, not trained in this project, and has no score on the
study's test set.

- **Test photos:** the study's held-out test set, 15 photos with 30 hands, scored for these two
  checkpoints. Among the study's YOLO26 models, x at 416 px scored best on it. The set is
  small, so a gap of this size is a clear lead rather than a proof. On cross-validation the
  two sizes are close (0.806 and 0.816, mean of three folds).
- **Time per frame:** measured here on 2026-10-30, in the light window with the model running
  at 30 frames per second. The camera delivers a frame every 33 ms: `s` and `x` keep up
  easily, `v8` only just. The v8 model is the smallest file but reads more per hand (the 21
  points), and the window's drawing slows it more (17 ms on its own). `main.py` ran it with
  PyTorch on the GPU, which takes 61 ms here, so it is exported to Core ML like the other
  two.
- **Getting them:** `s` is in the `models-v1` release ([MODELS.md](MODELS.md#download)). `x`
  is exported from the study's checkpoint:

  ```bash
  cp ~/Documents/MIDI-Dataset/v2-study/midi_results/weights/hbb-x-fold0-416.pt .
  uv run yolo export model=hbb-x-fold0-416.pt format=coreml imgsz=416
  rm hbb-x-fold0-416.pt
  ```

  The export was checked against the original on the 15 test photos: the same detections above
  confidence 0.6, and boxes within IoU 0.98.

  `v8` is exported from `yolov8n-hand-pose.pt` (in `~/Documents/MIDIproject`):

  ```bash
  cp ~/Documents/MIDIproject/yolov8n-hand-pose.pt .
  uv run yolo export model=yolov8n-hand-pose.pt format=coreml imgsz=384
  ```

  On 60 study photos at the app's confidence floor (0.7), the export and the original found
  the same real hands, with boxes within IoU 0.92 and points 2.4 % of a hand size apart on
  average. The original also found 6 boxes at the top edge of some photos where no hand is
  labelled; the export did not.

## How the pieces connect

```
MacBook Air camera, 640×480
  │
  ▼
src/vision_hbb.py      s or x (Core ML): a box and a gesture per hand
                       v8 (Core ML): a box and 21 points per hand
  │
  ▼
src/logic_obb.py       gestures → MIDI (s, x)
src/logic.py           gestures → MIDI (v8)
  ├─ right hand: notes, volume (CC 7) ──► IAC Driver Bus 1 ──► Cubase "All MIDI Inputs"
  │                                                           → the selected track → sound
  └─ left hand: CubaseTransport ────────► IAC Driver Bus 2 ──► MIDI Remote script
     (src/cubase_control.py, CC 102–105,                      → select track, record,
      110–117 on channel 16)                                    cycle, stop, to left locator
```

Notes are on MIDI channel 1. Volume is sent only when it changes, so recordings are not filled
with repeats. In Theremin mode the pitch is sent as pitch bend.

## One-time setup

### 1. The Mac: two IAC buses

Audio MIDI Setup → Window → Show MIDI Studio → double-click **IAC Driver**:
- tick "Device is online";
- under Ports, make sure there are two: `Bus 1` and `Bus 2` (`+` adds one).

### 2. The project

```bash
cd ~/Documents/gesture-midi-instrument
uv sync
uv run python tests/check_headless.py     # ends with ALL PASS
```

Put `hbb-s-fold1-320.mlpackage`, and `hbb-x-fold0-416.mlpackage` for `--model x`, in this
folder (see [Models](#models)). The first run asks for camera permission.

### 3. Cubase

**MIDI Remote script.** Copy it in, then restart Cubase:

```bash
cp -R cubase/midi_remote/indigo ~/Documents/Steinberg/"Cubase LE AI Elements"/"MIDI Remote"/"Driver Scripts"/Local/
```

Studio → MIDI Remote Manager should list **GestureInstrument** (vendor Indigo) once:
- status Connected, input port `IAC Driver Bus 2`;
- 5 transport buttons (record, cycle, stop, to left locator, set right locator) and 8 track
  buttons, none marked "Missing".

If it is not listed, use "Add Surface" and choose Indigo → GestureInstrument. After copying a
changed script, press the reload button (↻).

**MIDI Port Setup** (Studio → Studio Setup → MIDI Port Setup):

| Port | Visible | In 'All MIDI Inputs' |
|---|---|---|
| IAC Driver Bus 1, In | ✓ | ✓: the notes reach the tracks |
| IAC Driver Bus 2, In | ✓ | **✗**: control messages must not be recorded |
| IAC Driver Bus 1 and 2, Out | ✗ | — |

Hiding the outputs keeps you from choosing them as a track's output, which would send MIDI in
a loop.

**Preferences** (Cubase LE AI Elements 13 menu → Preferences):
- Editing → Project & MixConsole → **Enable Record on Selected MIDI Track**: on. Clicking a
  track then arms it, and that track plays the right hand.
- MIDI → **MIDI Thru Active**: on.

#### Audio

Studio → Studio Setup → Audio System → Built-in Audio:
- the page shows Input and Output Latency;
- **Control Panel** sets the buffer size. A smaller buffer means less delay: try 128 or 256
  samples, and go one step up if the sound crackles;
- on the Audio System page, turn "Release Driver when Application is in Background" off, so
  Cubase keeps the audio while the instrument window is in front.

#### Tracks

- One instrument track per layer, in the order you will record them: for example Groove Agent
  SE for drums first, then HALion Sonic with a bass, then a lead. The first loop always goes on
  the top instrument / MIDI track.
- On each: input **All MIDI Inputs** and **Monitor off**. With Monitor on, a track plays the
  right hand even when it is not selected.
- Do not arm tracks by hand (the red record button). Selecting a track arms it; a track armed
  by hand stays armed and records every layer too.
- Choose sounds inside the instrument as usual. HALion Sonic's GM Mode is not needed here.

#### Loop

- Put the left locator where the loop should start, for example bar 1. The right locator and
  the cycle are set by the second fist.
- Keep the loop area empty on the other tracks: anything already there plays along with your
  loops.
- MIDI cycle record mode **Keep Last** (Transport → MIDI Cycle Record Mode → Keep Last; the
  default is Mix). It keeps one complete pass of a layer and drops the unfinished pass after
  it. With Mix, the start of that second pass would be recorded on top of the first.
- **Auto Quantize (AQ) off**, so the notes stay where you played them.
- **Metronome click on, count-in off** (as set up here, at 100 BPM): the click plays while you
  record and while the loops play, and the first fist records at once. In the transport bar's
  metronome area (right end) these are the first two buttons: "Activate Metronome Click" (lit)
  and "Activate Count-in" (not lit). "Click while Recording" and "Click while Playing" in
  Metronome Setup choose when the click sounds.
- If you turn the count-in on, tell the app how long it is, since the app waits for it before
  re-sending a held note: for example
  `CUBASE_COUNT_IN_BARS=1 CUBASE_TEMPO=100 uv run python main_cubase_lite.py` (4 beats per bar
  unless `CUBASE_COUNT_IN_BEATS` says otherwise).

## Recording a take

1. Open the Cubase project. Check the tracks are in the order you want to record the layers.
2. Run `uv run python main_cubase_lite.py` (add `--model x` for the heaviest model) from
   `~/Documents/gesture-midi-instrument`. The Terminal should show `Connected to MIDI output:
   'IAC Driver Bus 1'` and `... 'IAC Driver Bus 2'`.
3. Check Scale, Root Note and Range: D, Minor, 1 or 2 octaves.
4. Hold the right hand where it should be silent, farthest from the camera, and press
   Calibrate.
   Without this, the place where the hand first appears becomes the silent point.
5. Play the layers: fist (record track 1), play, fist (it loops). Keep a fist for 2 seconds
   (record track 2), play over the first loop, fist (both loop). Repeat for more layers. Thumb
   out to stop.
6. For a retake, undo the recordings in Cubase (Cmd+Z) and start again with a fist.

## If something goes wrong

| Symptom | Cause and fix |
|---|---|
| `can't open file .../main_cubase_lite.py` | Run it from `~/Documents/gesture-midi-instrument` |
| `Gesture model not found` | The `.mlpackage` for the chosen `--model` is missing from the project folder |
| No sound | The track is not selected or armed, Bus 1 is not in "All MIDI Inputs", or MIDI Thru is off |
| Every track plays at once | Monitor is on for those tracks |
| A note keeps sounding after a track switch | Cubase menu MIDI → Reset. Switch tracks with the right hand out of view |
| A note held from before the fist is missing; only its volume bars are in the part | The app's count-in length does not match Cubase's (tempo, bars, or the count-in switched off). Set `CUBASE_TEMPO` / `CUBASE_COUNT_IN_BARS` to match |
| A layer ends a little before the loop end, leaving a gap | Fixed on 2026-10-31: layers now stop just after the loop comes round; set the MIDI cycle record mode to Keep Last |
| The start of a layer sounds doubled | The MIDI cycle record mode is Mix; set it to Keep Last |
| A long extra note rings under the others | Two causes, both fixed on 2026-10-31: Cubase's cycle stayed on during the first recording, so a take longer than the previous loop wrapped over its own start; and one-frame detection flickers made notes too short for Cubase to close. Restart the app |
| The first note of a loop plays quieter than recorded | Fixed on 2026-10-31: the volume is now sent before every note. Restart the app |
| The second layer lands after the first loop, not on top of it | Cycle was off (grey in the ruler), so Cubase played on past the loop. The app now waits 0.2 s before turning cycle on and turns it on again at every new layer; restart the app |
| After recording, the bars keep moving and your notes don't come back | An older copy of the Cubase script: the loop was the old cycle range, not your recording. Copy the current script and press ↻ in MIDI Remote Manager |
| A loop lands on the wrong track | A track was armed by hand, or the tracks are not in recording order. "Track 1" is the top instrument / MIDI track |
| The 2-second fist does nothing | It works only while a loop plays, with a fist that started then. Open the hand, then make a new fist and keep it |
| Playback stops by itself | The model read the left hand as a thumb. Keep the fist clear of the thumb, or open the hand between gestures |
| The fist does nothing | Check that MIDI Remote Manager shows the surface Connected on Bus 2. MIDI Remote → Scripting Tools: Open Console prints `Indigo record = 127` and so on for every message |
| A MIDI Remote button says "Missing", or a second, Disconnected surface appears | An older copy of the script. Copy the current one, remove the Disconnected entry, press ↻ |
| The sound feels late | Lower the audio buffer ([Audio](#audio)) |
| Too quiet or too loud | Calibrate again |

Useful while testing: `MIDI_LATENCY_DEBUG=1 uv run python main_cubase_lite.py` prints the
frame rate, the model's time per frame and how old each frame is when its MIDI is sent, every
5 seconds. `CAMERA_INDEX=1` picks another camera.

## Other versions

All of them share the same instrument logic. See the [README](../README.md#the-programs) for
details.

| Program | In one line |
|---|---|
| `main_cubase.py` | The full Cubase window: everything in the light version, plus an Instrument menu (HALion Sonic GM sounds), a Cubase Track menu, more range presets, volume sliders and overlay options |
| `main_obb.py` | The same instrument for any DAW or GarageBand, on one MIDI bus, with loops recorded inside the app |
| `main_rotate.py` | Pitch from tilting the right hand instead of its height |
| `main_mediapipe.py`, `main.py` | Earlier versions with other hand detectors |

### The three models

`--model s`, `x` and `v8` run the same instrument with the same settings; only the detector
and, for `v8`, the gesture logic differ. `v8` is where the instrument started: a general
hand-pose model whose gestures are worked out from finger points. `s` and `x` were trained on
this project's own photos to recognise the three gestures directly.

#### The standard and the heaviest model

`--model s` and `--model x` run the same instrument with the same settings; only the detector
differs. The x model has about 6 times the parameters (58.8 M against 10.0 M), reads the
picture at 416 px instead of 320, and is the more accurate of the two on the study's test photos. It takes about 24 ms per
frame instead of 7, so each note reaches Cubase about 17 ms later, still within one camera
frame. The study chose the s model for everyday use because it stays under 10 ms per frame
even after 15 minutes of continuous playing on this fanless Mac.

### The light window and the full Cubase window

The two Cubase programs are the same instrument. They use the same model, logic, buses and
Cubase script. They differ in the window.

The full window enlarges every camera frame to fill the screen, and builds a new image for each
frame. The light window shows the frame at the camera's own size and reuses one image. Measured
on this Mac on 2026-10-29, with the model running at 30 frames per second on a test frame:

| | Drawing one frame | Model time per frame (average / slowest 5 %) |
|---|---|---|
| No window | — | 10.0 ms / 11.8 ms |
| Full window, maximised | 95 ms | 18.9 ms / 44.4 ms |
| Light window | 29 ms | 9.1 ms / 15.1 ms |

The full window redraws every 40 ms but needs 95 ms to draw. That kept its menus from
responding, and slowed the gesture model running beside it. The light window leaves the model
close to its speed with no window. Cubase's audio output latency comes on top of both.
