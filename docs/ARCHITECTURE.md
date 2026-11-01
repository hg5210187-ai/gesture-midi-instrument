# Architecture

How the parts fit, what each one promises the next, and every number that can be tuned.

## The pipeline

```
camera ──► vision_*.py ──► logic*.py ──► midi_engine.py ──► MIDI port ──► DAW / synth
            (frame, result)     │   ▲
                 │              ▼   │
                 │           looper.py        records live events, replays them on channel 2
                 ▼
            overlay.py ──► frame queue (size 2) ──► ui.py
```

One frame goes through it like this: the vision module returns a mirrored frame and a
detection result; the logic turns the result into MIDI messages and remembers what it saw;
the overlay draws that memory onto the frame; the frame is queued for the window.

## Which files make each program

| Program | Vision class | Logic module | What the logic receives |
|---|---|---|---|
| `main_mediapipe.py` | `MediaPipeVision` (`src/vision_mediapipe.py`) | `src/logic.py` | An object shaped like an Ultralytics pose result |
| `main.py` | `UltralyticsVision` (`src/vision_ultralytics.py`) | `src/logic.py` | Ultralytics pose result: boxes + 21 keypoints per hand |
| `main_rotate.py` | `Yolo26Vision` (`src/vision_yolo26.py`) | `src/logic_rotate.py` | Ultralytics OBB result: oriented boxes + class |
| `main_obb.py` | `HbbVision` (`src/vision_hbb.py`) | `src/logic_obb.py` | Ultralytics detect result: boxes + class |
| `main_cubase.py` | `HbbVision` (`src/vision_hbb.py`) | `src/logic_obb.py` | Ultralytics detect result: boxes + class |
| `main_cubase_lite.py` | `HbbVision` (`src/vision_hbb.py`) | `src/logic_obb.py` | Ultralytics detect result: boxes + class |

`src/midi_engine.py`, `src/scales.py`, `src/ui.py` and `src/overlay.py` are shared by all
six (`main_cubase_lite.py` takes only the scale and note lists from `src/ui.py`; its window is
`src/ui_lite.py`). `src/looper.py` is used by all but `main_cubase.py`, which passes a `CubaseTransport`
(`src/cubase_control.py`) to the logic in its place. See [Cubase version](#cubase-version).

### The two contracts

**Vision.** `get_frame()` returns `(success, frame, result)`. `frame` is BGR, mirrored, and
not drawn on. `release()` closes the camera.

**Logic.** `process(result)` sends MIDI through the engine it was constructed with and leaves
its view of the frame in attributes that the overlay reads:

| Attribute | Meaning |
|---|---|
| `last_right_bbox`, `last_left_bbox` | Normalised `[x1, y1, x2, y2]`, or `None` |
| `last_right_obb` | Four normalised corners of a rotated box, where the model gives one |
| `last_hand_y_norm` | Right-hand height after the reach stretch, 0 = bottom, 1 = top |
| `current_pitch_note` | The MIDI note sounding now, or `-1` |
| `scale`, `scale_type`, `play_margin` | What the pitch bands are drawn from |
| `show_borderlines`, `show_pitch` | The two overlay checkboxes |
| `pitch_from_rotation`, `last_angle_t`, `last_angle_deg`, `rotation_mode` | Rotation instrument only: draw the dial instead of the height guides |

A new detector needs one new vision file that honours the first contract. A new way of
playing needs one new logic file that honours the second. `src/vision_mediapipe.py` shows the
cheapest form of the first: it wraps MediaPipe's output in four tiny classes so the existing
logic cannot tell the difference.

## Threads

| Thread | What runs in it |
|---|---|
| Main | The Tk event loop. Every 40 ms `update_ui_video` takes one frame from the queue, shows it, and refreshes the looper label. Only this thread touches widgets |
| Vision (daemon) | `MIDIApp.vision_loop`: `get_frame` → `logic.process` → `render_overlay` → queue. Each frame is inside its own `try`; the loop stops after 60 consecutive errors |
| Settings worker (daemon) | Applies settings from the UI to the logic and the MIDI engine. If several changes are queued, only the newest is applied |
| Looper playback (daemon) | Exists only while the looper is `PLAYING` |
| Camera capture (daemon) | `main_obb.py` only. Keeps the newest mirrored frame; `get_frame` blocks until it is newer than the last one returned |

The frame queue holds two frames. When it is full the vision thread drops the frame rather
than wait, so the picture cannot fall behind the hands.

`main.py`, `main_mediapipe.py` and `main_rotate.py` pace the vision loop to 20 fps
(`target_fps`). `main_obb.py` has no pacing and runs at the camera's rate.

## Telling the hands apart

No program uses true handedness. The frame is mirrored, so the player's right hand appears on
the right.

- `src/logic.py`: detections are sorted by box centre X. With two or more, the leftmost is
  the left hand and the rightmost the right. With one, the half of the picture decides.
- `src/logic_obb.py`, `src/logic_rotate.py`: the rightmost box **on the right half** is the
  right hand and the leftmost box **on the left half** is the left hand. A box on the wrong
  half never takes the other hand's role.

## Right hand → pitch and volume

Height programs (`logic.py`, `logic_obb.py`):

```
y      = 1 − box_centre_y                                    up = higher
y      = clamp((y − play_margin) / (1 − 2·play_margin))      stretch the reachable band
note   = scale[int(y · len(scale))]                          scale mode
bend   = int(y · 16383) − 8192, held note C4                 Theremin mode

volume = clamp((area / area_min − 1) · gain) · 127           sent as CC 7
gate   = volume > volume_gate                                closed → note off
```

Rotation program (`logic_rotate.py`):

```
a      = recentre and unwrap the box angle                   vertical hand = 0, range ±90°
t      = clamp((a − angle_min) / (angle_max − angle_min))
note   = scale[int(t · len(scale))]                          Scale mode
exact  = scale[0] + t · (scale[−1] − scale[0])               Continuous mode:
note   = round(exact), bend = (exact − note) · 100 / 200 · 8192
```

Volume and the gate are the same in every program.

## MIDI that leaves the program

| Message | Sent when | Channel |
|---|---|---|
| Note on, velocity 64 | The gate is open and the note changes | 1 |
| Note off | The note changes, the gate closes, or the right hand disappears | 1 |
| Control change 7 | Every frame that has a right hand, value 0–127 | 1 |
| Pitch bend | Theremin mode and rotation Continuous mode, while the gate is open. The rotation program also sends one bend back to centre when the note stops | 1 |
| Program change | The Instrument menu changes | 1 and 2 |
| Everything the looper recorded | During loop playback | 2 |

Loudness is carried by CC 7, not by velocity. The Theremin mode sends the full bend range, so
how far the pitch travels depends on the bend range set in the synth; at the common default
of ±2 semitones it covers C4 ± 2 semitones. The Continuous rotation mode assumes ±2
semitones.

**Port selection** (`MidiEngine.__init__`): a port whose name contains `MIDI_PORT`, if set;
else the first port containing `IAC`; else a new virtual port named
`Indigo Gesture Controller`; and if that fails, the first port available. With `port=` (used
only by `main_cubase.py`) it opens exactly that port or none, never a fallback.

## Cubase version

`main_cubase.py` sends to two ports by exact name:

| Port | Messages |
|---|---|
| `IAC Driver Bus 1` (`CUBASE_NOTES_PORT`) | The table above on channel 1, except: CC 7 only when its value changes (`dedupe_cc=(7,)`), Program Change on channel 1 only, and CC 123 (All Notes Off) before a track switch |
| `IAC Driver Bus 2` (`CUBASE_CONTROL_PORT`) | Control changes on channel 16 for the MIDI Remote script `cubase/midi_remote/indigo/gestureinstrument/Indigo_GestureInstrument.js` |

`CubaseTransport` has the looper's interface: `state` (`IDLE` / `RECORDING` / `PLAYING`),
`toggle()` returning the new state, `record_event()` (does nothing), `cleanup()`, plus a
`label` property for the overlay badge (`CUBASE`, or `CUBASE T2` with the loop's track) and
`select_track(i)`. It also has `hold()` and `stop()`. `GestureLogic` calls them only on a
looper that has them, so the in-app looper is unaffected: `hold()` when the fist that toggled
is still held after `_hold_seconds` (2.0), `stop()` on a left `thumbout` held
`_thumb_confirm_frames` (8, against 5 for the fist, because the detector confuses the two
classes).

| Gesture, step | Control changes sent (CC, value) |
|---|---|
| fist, IDLE → RECORDING | select the start track (110 + i: 0, 127), cycle off (103: 127, 0), `CYCLE_OFF_SETTLE_S` (0.15 s), go to left locator (105: 127, 0), record (102: 0, 127). Sent without the pause, the cycle off was ignored (screen recording, 2026-10-31): the first recording ran inside the previous cycle and could wrap over its own start. Recording starts from a stop, so Cubase's count-in, if on, plays first |
| fist, first RECORDING → PLAYING | set right locator (106: 127, 0), record off (102: 0); `LOOP_START_DELAY_S` (0.2 s) later, on a timer thread and only if still PLAYING: cycle on (103: 0, 127), go to left locator (105: 127, 0). The first recording's length becomes the cycle. Sent together with the record-off, the last two were dropped by Cubase |
| fist, later RECORDING → PLAYING | record off (102: 0) |
| fist, PLAYING | nothing; arms `hold()` for this fist |
| fist kept 2 s, PLAYING → RECORDING | select the next track, up to track 8 (110 + i: 0, 127), cycle on (103: 0, 127), go to left locator (105: 127, 0); `LAYER_RECORD_DELAY_S` (0.15 s) later, if this recording is still on: record (102: 0, 127). Sent together, Cubase punched in before it moved, so layers started wherever the loop was. The held-note re-send waits for this too |
| one loop pass later, RECORDING → PLAYING | record off (102: 0), on a timer thread: `loop_s` (measured from the first recording's record command to the fist that closed it, which includes Cubase's ~0.15 s start-up) plus `LAYER_STOP_AFTER_S` (0.3 s): just after the loop comes round. Cubase's MIDI Cycle Record Mode must be Keep Last, which keeps the last complete pass and drops the unfinished one, so the layer is exactly one loop long. Stopping just before the end (the first version) left a ~0.2 s gap. Skipped if that recording already ended or another has started (`_take`) |
| thumb out, any → IDLE | record off if recording (102: 0), stop (104: 127, 0) |
| `select_track(i)`, i = 0–7 | 110 + i: 0, 127; also makes i the start track |
| `cleanup()` when not idle | as thumb out |

Selecting and then recording waits `SELECT_SETTLE_S` (50 ms) in between, so Cubase has armed
the new track ("Enable Record on Selected MIDI Track") before record starts. A fist seen again
after a dropout shorter than the release debounce is the same fist: it neither toggles again
nor restarts the hold timer.

How the design avoids the obvious failures:

- **No toggles.** Record and cycle are plain value bindings in the script; stop and go to
  left locator are command bindings. The app's state can go stale (Cubase stopped by hand),
  but no message can flip Cubase into the opposite state. "On" sends 0 before 127 so it is a
  change even if the script's copy of the value is already 127.
- **No feedback loop.** The script declares an input only. Anything Cubase sent to Bus 2
  would come straight back in on Bus 2.
- **No control messages in recordings.** Bus 2 must be out of "All MIDI Inputs", and the
  script's bindings consume their messages.
- **No stuck note on a track switch.** The UI records the chosen track; the vision thread
  applies it before its next frame: releases the note, sends CC 123, clears the CC 7 cache,
  then selects. All note traffic stays on the vision thread.
- **Held notes are recorded.** Cubase records only notes that start while it records, so a
  note held when recording starts would leave only its CC 7 changes in the part. After each
  frame the vision thread watches the transport state and, once it is RECORDING, sends the
  held note again: note off, the last CC 7 (`MidiEngine.resend_cc`), note on. After a
  2-second fist (a punch-in while playing) that is `RETRIGGER_DELAY_S` (0.15 s) later; after
  the first fist (from a stop, which takes Cubase a moment) `RETRIGGER_FROM_STOP_S` (0.2 s)
  plus `COUNT_IN_S`, 0 unless `CUBASE_COUNT_IN_BARS` is set. Cubase's MIDI record catch range
  (100 ms here) places a note that arrives just before recording starts at its start.
- **No very short notes.** A one-frame detection flicker made notes of 0.03–0.06 s, and Cubase
  sometimes lost their ends, so they rang under the rest of the part. The Cubase apps set
  `GestureLogic.min_note_s` to 0.08 s (`MIN_NOTE_S`): the pitch does not change until the
  current note has lasted that long. The gate still cuts a note at once. Default 0 elsewhere.
- **Each note carries its volume.** CC 7 is de-duplicated, and the logic used to send it after
  the note-on, so a note whose volume had not changed was recorded without one and, looped,
  played at the volume the previous pass ended on. Both logic modules now send CC 7 right
  before every note-on, forced past the de-duplication (`MidiEngine.send_cc_forced`).
- **Thread safety.** A lock keeps each message sequence whole, since rtmidi output is not
  locked and the main thread's `cleanup()` can run during a frame. `cleanup()` runs twice and
  sends nothing the second time.

The track bank is `makeMixerBankZone().includeInstrumentChannels().includeSamplerChannels()
.includeMIDIChannels()`, so "Track 1" is the first such track in MixConsole order, not the
first track in the project.

**Light version.** `main_cubase_lite.py` subclasses `CubaseApp` and overrides `_make_ui()`,
returning `LiteUI` (`src/ui_lite.py`) instead of `SettingsUI`, and `_make_vision()` /
`_make_logic()` for `--model`. With `--model v8` the vision is `HbbVision(task="pose")` on
`yolov8n-hand-pose.mlpackage` and the logic is `src/logic.py`, whose `_static_frames` is raised
to 90 (3 s) so a still 2-second fist is not muted as a background phantom. `src/logic.py`
reads thumb out from the keypoints (`_is_thumb_out`: a fist whose thumb tip is more than one
hand size from the palm) and has the same hold, thumb and dropout handling as
`src/logic_obb.py`, active only with a looper that has `hold()`; with the in-app looper its
left hand behaves as before. `LiteUI` has the
methods the app calls (`update_image`, `update_looper_status`, `set_calib_status`) and passes
`update_settings` a dictionary with only scale, root and range (1 or 2 octaves) chosen; the
rest is fixed (`FIXED_SETTINGS`), and there is no `instrument_program`, so no Program Change is
sent. `CubaseLiteApp.update_settings` adds the root an octave (or two) up after the scale is
built, because `ScaleGenerator` stops one step below it; theremin mode is left alone. The
picture is pasted at 640×480 into one reused `ImageTk.PhotoImage` on a plain Tk label, instead
of a new `CTkImage` scaled to the panel for every frame.

## Looper

`IDLE → RECORDING → PLAYING → IDLE`, one step per confirmed left-hand fist.

- Events are stored as `(seconds since recording began, type, data)`.
- Recorded types: note on, note off, CC, pitch bend.
- Playback sleeps on a `threading.Event` between events, so stopping is immediate.
- All sounding notes are turned off at each loop boundary and when playback stops.
- A recording with no events or shorter than 0.3 s goes back to `IDLE`.

## Constants

| | `logic.py` | `logic_obb.py` | `logic_rotate.py` |
|---|---|---|---|
| Used by | `main.py`, `main_mediapipe.py` | `main_obb.py` | `main_rotate.py` |
| `min_confidence` | 0.7 | 0.6 | 0.5 |
| `max_box_area` (fraction of frame) | none | 0.30 | 0.35 |
| `play_margin` | 0.15 | 0.15 | not used |
| `volume_gain` default | 2.0 | 2.0 | 2.0 |
| `volume_gate` default | 8 | 8 | 8 |
| Fist test | fingertip-to-palm ratio < 0.65 | class `closedhand` | class `closedhand` |
| Frames a fist must be held | 3 | 5 | 3 |
| Frames absent before the fist is released | 1 | 5 | 3 |
| Cooldown between looper toggles | 1.0 s | 1.0 s | 1.0 s |
| Stationary-box rejection | 30 sightings within 0.012 | none | none |
| Smallest bend change recorded in a loop | 200 | 200 | 100 |
| Smallest volume change recorded in a loop | 5 | 5 | 5 |

| Elsewhere | Value | Where |
|---|---|---|
| Camera capture size | 640 × 480 | every vision module in use |
| Inference size | 384 (`main.py`), 640 (`main_rotate.py`), 320 (`main_obb.py`) | vision modules |
| Vision loop pacing | 20 fps, or camera rate in `main_obb.py` | `main*.py` |
| Video refresh | every 40 ms | `main*.py` |
| Frame queue | 2 | `main*.py` |
| Consecutive frame errors before stopping | 60 | `main*.py` |
| Shortest loop kept | 0.3 s | `src/looper.py` |
| Most band lines drawn | 24 | `src/overlay.py` |

## Leftovers

Kept because removing them was never the task at hand:

- **Number of Tracks slider.** From the first version, which selected GarageBand tracks. Its
  value still enters the settings dictionary as `tracks`; nothing reads it. `main_cubase.py`
  shows the Cubase Track menu in its place.
- **`src/vision.py`.** The original MediaPipe backend. It uses `mediapipe.solutions`, which
  the pinned MediaPipe no longer has.
- **The two-model backend.** `UltralyticsVision` in `src/vision_obb.py` (a right-hand
  oriented-box model plus a left-hand pose model) and the matching `_extract_right_obb` and
  `_extract_left_pose` in `src/logic_obb.py`. No program creates it now; `main_obb.py` uses
  `HbbVision`, which reuses only the camera thread from that file.
- **The benchmark path in `map_pitch`.** `src/logic.py` and `src/logic_obb.py` can map height
  in centimetres per octave when `experiment_sensitivity` or `experiment_scale_type` is set.
  Only `run_benchmark.py` sets them.
