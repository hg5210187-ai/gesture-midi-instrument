"""Headless checks of the instrument logic (no camera, no MIDI port, no UI).

    uv run python tests/check_headless.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np


class FakeMidi:
    def __init__(self):
        self.log = []

    def send_note_on(self, note, velocity=64, channel=0):
        self.log.append(("on", note, channel))

    def send_note_off(self, note, velocity=0, channel=0):
        self.log.append(("off", note, channel))

    def send_cc(self, control, value, channel=0):
        self.log.append(("cc", control, value, channel))

    def send_pitch_bend(self, pitch, channel=0):
        self.log.append(("bend", pitch, channel))

    def send_program_change(self, program, channel=0):
        self.log.append(("pc", program, channel))

    def notes_on(self):
        return [e[1] for e in self.log if e[0] == "on"]

    def last_cc(self):
        return [e[2] for e in self.log if e[0] == "cc"][-1]


class T:
    def __init__(self, a):
        self.a = np.asarray(a)

    def cpu(self):
        return self

    def numpy(self):
        return self.a


class Boxes:
    def __init__(self, xyxyn, conf, cls=None):
        self.xyxyn, self.conf = T(xyxyn), T(conf)
        if cls is not None:
            self.cls = T(cls)

    def __len__(self):
        return len(self.xyxyn.a)


class Kpts:
    def __init__(self, xyn):
        self.xyn = T(xyn)

    def __len__(self):
        return len(self.xyn.a)


class Obb:
    def __init__(self, xywhr, polys, conf, cls):
        self.xywhr, self.xyxyxyxyn = T(xywhr), T(polys)
        self.conf, self.cls = T(conf), T(cls)

    def __len__(self):
        return len(self.xywhr.a)


class Res:
    pass


NAMES = {0: "thumbout", 1: "openhand", 2: "closedhand"}
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {detail}")


def box(cx, cy, w=0.2, h=0.3):
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def open_hand_kpts(cx, cy):
    k = np.zeros((21, 2))
    k[0] = [cx, cy + 0.10]           # wrist
    k[9] = [cx, cy]                  # middle knuckle
    for tip in (8, 12, 16, 20):
        k[tip] = [cx, cy - 0.20]     # fingertips far from the palm
    return k


def fist_kpts(cx, cy):
    k = open_hand_kpts(cx, cy)
    for tip in (4, 8, 12, 16, 20):
        k[tip] = [cx, cy + 0.05]     # thumb and fingertips on the palm centre
    return k


def thumb_out_kpts(cx, cy):
    k = fist_kpts(cx, cy)
    k[4] = [cx + 0.15, cy]           # thumb tip 1.6 hand sizes from the palm
    return k


# --------------------------------------------------------------------------
print("1. entry points import (no app constructed)")
for mod in ("main", "main_mediapipe", "main_obb", "main_rotate", "main_cubase", "main_cubase_lite",
            "run_benchmark"):
    try:
        __import__(mod)
        check(mod, True)
    except Exception as e:                      # noqa: BLE001
        check(mod, False, repr(e))

from src.looper import MidiLooper
from src.overlay import render_overlay
from src.scales import ScaleGenerator, midi_to_freq, midi_to_name_octave

print("2. scales")
check("A minor pentatonic starts at A2=45",
      ScaleGenerator.get_scale("A", "minor_pentatonic")[:5] == [45, 48, 50, 52, 55])
check("default 5 octaves of chromatic = 60 notes",
      len(ScaleGenerator.get_scale("C", "chromatic")) == 60)
check("69 -> A4 / 440 Hz",
      midi_to_name_octave(69) == "A4" and abs(midi_to_freq(69) - 440) < 1e-9)

# --------------------------------------------------------------------------
print("3. src/logic.py  (pose path: main.py / main_mediapipe.py)")
from src.logic import GestureLogic as PoseLogic


def pose_result(hands):
    """hands: list of (bbox, conf, kpts)."""
    r = Res()
    r.boxes = Boxes([h[0] for h in hands], [h[1] for h in hands])
    r.keypoints = Kpts([h[2] for h in hands])
    r.orig_shape = (480, 640)
    return r


def right_only(cy, w=0.2, h=0.3, conf=0.95):
    return pose_result([(box(0.75, cy, w, h), conf, open_hand_kpts(0.75, cy))])


m = FakeMidi()
lg = PoseLogic(m, MidiLooper(m, channel=1))
lg.process(right_only(0.5, 0.10, 0.15))       # small hand seeds area_min
check("first frame seeds area_min, gate shut (no note)", m.notes_on() == [])
lg.process(right_only(0.15))                  # big hand at the TOP edge of reach
check("hand at top -> highest scale note (57)", m.notes_on()[-1:] == [57], str(m.notes_on()))
lg.process(right_only(0.85))                  # BOTTOM edge of reach
check("hand at bottom -> lowest scale note (45)", m.notes_on()[-1:] == [45], str(m.notes_on()))
check("volume sent as CC7 and > gate", m.last_cc() > lg.volume_gate, str(m.last_cc()))
lg.process(right_only(0.85, conf=0.30))       # below min_confidence
check("low-confidence box is dropped -> note released",
      lg.current_pitch_note == -1 and m.log[-1][0] != "on")

m = FakeMidi()
looper = MidiLooper(m, channel=1)
lg = PoseLogic(m, looper)
states = []
for i in range(4):
    jit = 0.02 * i                            # jitter so the box is not "stationary"
    lg.process(pose_result([(box(0.25 + jit, 0.5), 0.95, fist_kpts(0.25 + jit, 0.5))]))
    states.append(looper.state)
check("left fist toggles looper only on the 3rd consecutive frame",
      states == ["IDLE", "IDLE", "RECORDING", "RECORDING"], str(states))
check("fist confirm frames == 3", lg._fist_confirm_frames == 3)
check("min_confidence == 0.7, play_margin == 0.15",
      lg.min_confidence == 0.7 and lg.play_margin == 0.15)

# stationary phantom: a perfectly still, confident right-side box goes silent
m = FakeMidi()
lg = PoseLogic(m, None)
lg.process(right_only(0.5, 0.10, 0.15))
for _ in range(40):
    lg.process(right_only(0.3))
check("motionless box is suppressed after ~30 frames",
      lg.current_pitch_note == -1 and lg.last_right_bbox is None)

# theremin: held C4 + full-range bend
m = FakeMidi()
lg = PoseLogic(m, None)
lg.scale_type = "theremin"
lg.process(right_only(0.5, 0.10, 0.15))
lg.process(right_only(0.15))
bends = [e[1] for e in m.log if e[0] == "bend"]
check("theremin holds C4 (60) and bends to +8191 at the top",
      m.notes_on() == [60] and bends[-1] == 8191, f"{m.notes_on()} {bends[-1:]}")

frame = np.zeros((480, 640, 3), np.uint8)
lg.show_borderlines = True
render_overlay(frame, lg)
check("overlay renders (pose logic)", frame.any())

# --------------------------------------------------------------------------
print("4. src/logic_obb.py  (single gesture detector: main_obb.py)")
from src.logic_obb import GestureLogic as HbbLogic


def det_result(dets):
    """dets: list of (bbox, conf, cls)."""
    r = Res()
    r.boxes = Boxes([d[0] for d in dets], [d[1] for d in dets], [d[2] for d in dets])
    r.names = NAMES
    r.orig_shape = (480, 640)
    return r


m = FakeMidi()
looper = MidiLooper(m, channel=1)
lg = HbbLogic(m, looper)
lg.process(det_result([(box(0.75, 0.5, 0.10, 0.15), 0.9, 1)]))
lg.process(det_result([(box(0.75, 0.15), 0.9, 1)]))
check("right-hand box at top -> 57", m.notes_on()[-1:] == [57], str(m.notes_on()))
lg.process(det_result([(box(0.75, 0.5, 0.7, 0.7), 0.9, 1)]))   # area 0.49 > 0.30
check("background-sized box rejected (max_box_area 0.30)", lg.current_pitch_note == -1)
states = []
for _ in range(6):
    lg.process(det_result([(box(0.25, 0.5), 0.9, 2)]))          # left closedhand
    states.append(looper.state)
check("left closedhand toggles looper on the 5th frame",
      states == ["IDLE"] * 4 + ["RECORDING"] * 2, str(states))
check("defaults: min_confidence 0.6, confirm 5, release 5",
      lg.min_confidence == 0.6 and lg._fist_confirm_frames == 5
      and lg._fist_release_frames == 5)
lg2 = HbbLogic(FakeMidi(), None)
lg2.process(det_result([(box(0.25, 0.5), 0.9, 1)]))            # left open hand only
check("left half never plays a note", lg2.current_pitch_note == -1)

# --------------------------------------------------------------------------
print("5. src/logic_rotate.py  (rotation instrument: main_rotate.py)")
from src.logic_rotate import GestureLogic as RotLogic


def obb_result(dets):
    """dets: list of (cx, cy, w, h, r, conf, cls) in normalized units."""
    W, H = 640, 480
    r = Res()
    xywhr, polys = [], []
    for cx, cy, w, h, rot, _, _ in dets:
        xywhr.append([cx * W, cy * H, w * W, h * H, rot])
        polys.append([[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2],
                      [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]])
    r.obb = Obb(xywhr, polys, [d[5] for d in dets], [d[6] for d in dets])
    r.orig_shape = (H, W)
    return r


m = FakeMidi()
lg = RotLogic(m, None)
lg.process(obb_result([(0.75, 0.5, 0.10, 0.15, 0.0, 0.9, 0)]))   # seed area_min
lg.process(obb_result([(0.75, 0.5, 0.20, 0.30, 0.0, 0.9, 0)]))   # vertical hand
mid = m.notes_on()[-1]
check("vertical hand (angle 0) -> middle of the scale (51)", mid == 51, str(mid))
check("angle window defaults to +/-90 deg",
      abs(lg.angle_min + math.pi / 2) < 1e-9 and abs(lg.angle_max - math.pi / 2) < 1e-9)
lg.process(obb_result([(0.75, 0.5, 0.20, 0.30, 0.6, 0.9, 0)]))   # rotate ~+34 deg
check("rotating changes the note", m.notes_on()[-1] != mid, str(m.notes_on()))
lg.rotation_mode = "continuous"
lg.process(obb_result([(0.75, 0.5, 0.20, 0.30, 0.65, 0.9, 0)]))
check("continuous mode sends pitch bend", any(e[0] == "bend" for e in m.log))
frame = np.zeros((480, 640, 3), np.uint8)
render_overlay(frame, lg)
check("overlay renders the rotation gauge", frame.any())

# --------------------------------------------------------------------------
print("6. src/cubase_control.py + MidiEngine options  (Cubase version: main_cubase.py)")
from src import cubase_control as cc
from src.cubase_control import CubaseTransport
from src.midi_engine import MidiEngine


def sent(fake):
    return [(e[1], e[2]) for e in fake.log if e[0] == "cc" and e[3] == cc.CONTROL_CHANNEL]


cc.SELECT_SETTLE_S = 0          # no pauses in the checks (the delayed path is checked below)
cc.LOOP_START_DELAY_S = 0
cc.LAYER_RECORD_DELAY_S = 0
cc.CYCLE_OFF_SETTLE_S = 0
m = FakeMidi()
cub = CubaseTransport(m)
check("IDLE -> RECORDING: select track 1, cycle off, go to left locator, record on (from a stop)",
      cub.toggle() == "RECORDING" and sent(m) == [(110, 0), (110, 127), (103, 127), (103, 0),
                                                 (105, 127), (105, 0), (102, 0), (102, 127)],
      str(sent(m)))
m.log.clear()
check("first recording -> PLAYING: right locator here, record off, cycle on, back to start",
      cub.toggle() == "PLAYING" and sent(m) == [(106, 127), (106, 0), (102, 0), (103, 0), (103, 127),
                                                (105, 127), (105, 0)], str(sent(m)))
m.log.clear()
check("hold() of the fist that started playback does nothing",
      cub.hold() == "PLAYING" and sent(m) == [])
check("short fist while PLAYING: nothing sent, the loop keeps playing",
      cub.toggle() == "PLAYING" and sent(m) == [])
check("fist held while PLAYING: select track 2, cycle on, back to the start, record on",
      cub.hold() == "RECORDING" and sent(m) == [(111, 0), (111, 127), (103, 0), (103, 127),
                                                (105, 127), (105, 0), (102, 0), (102, 127)]
      and cub.track == 1 and cub.label == "CUBASE T2", str(sent(m)))
m.log.clear()
check("a later recording -> PLAYING: record off only, the loop length stays",
      cub.toggle() == "PLAYING" and sent(m) == [(102, 0)], str(sent(m)))
cub.toggle(); cub.hold()                             # record track 3
m.log.clear()
check("thumb out while RECORDING: record off + stop",
      cub.stop() == "IDLE" and sent(m) == [(102, 0), (104, 127), (104, 0)] and cub.label == "CUBASE",
      str(sent(m)))
m.log.clear()
cub.cleanup()
check("cleanup from IDLE sends nothing", sent(m) == [])
import time as _time
cc.LOOP_START_DELAY_S = 0.05
m2 = FakeMidi()
cub2 = CubaseTransport(m2)
cub2.toggle(); m2.log.clear(); cub2.toggle()
at_once = sent(m2)
_time.sleep(0.15)
check("loop start waits 0.2 s after the record-off (cycle on, back to start come later)",
      at_once == [(106, 127), (106, 0), (102, 0)]
      and sent(m2) == at_once + [(103, 0), (103, 127), (105, 127), (105, 0)], str(sent(m2)))
cub2.toggle(); m2.log.clear(); cub2.toggle(); cub2.stop()
_time.sleep(0.15)
check("a stop before the loop starts cancels it", (103, 127) not in sent(m2), str(sent(m2)))
cc.LOOP_START_DELAY_S = 0

# A layer jumps to the loop's start first and switches record on a moment later.
cc.LAYER_RECORD_DELAY_S = 0.05
m6 = FakeMidi()
c6 = CubaseTransport(m6)
c6.toggle(); c6.toggle(); c6.toggle()                # first loop closed, fist while playing
c6.loop_s = 10                                       # a real-length loop: no automatic stop here
m6.log.clear()
c6.hold()
at_once = sent(m6)
_time.sleep(0.12)
check("a new layer jumps to the start first; record on comes after",
      at_once == [(111, 0), (111, 127), (103, 0), (103, 127), (105, 127), (105, 0)]
      and sent(m6) == at_once + [(102, 0), (102, 127)], str(sent(m6)))
c6.toggle(); c6.toggle(); m6.log.clear()
c6.hold(); c6.toggle()                               # a fist before record on came
_time.sleep(0.12)
check("a fist right after the jump cancels the layer's record on",
      (102, 127) not in sent(m6), str(sent(m6)))
c6.stop()
cc.LAYER_RECORD_DELAY_S = 0

# A layer stops recording by itself after one pass of the loop.
cc.LAYER_STOP_AFTER_S = 0                            # stop right at one pass in the check
m5 = FakeMidi()
c5 = CubaseTransport(m5)
c5.toggle(); _time.sleep(0.12); c5.toggle()          # first recording: a 0.12 s loop
measured = c5.loop_s
c5.toggle(); c5.hold(); m5.log.clear()               # a layer starts recording
_time.sleep(0.3)
check("a layer stops by itself after one pass (record off only), the loop plays on",
      0.1 <= measured < 0.2 and c5.state == "PLAYING" and sent(m5) == [(102, 0)],
      f"{measured:.3f} s {sent(m5)}")
c5.toggle(); c5.hold(); c5.toggle(); m5.log.clear()  # a layer stopped early with a fist
_time.sleep(0.3)
check("a layer already stopped with a fist is not stopped again", sent(m5) == [], str(sent(m5)))
c5.toggle(); c5.hold(); c5.stop(); c5.toggle(); m5.log.clear()   # thumb out, then a new first take
_time.sleep(0.3)
check("an old layer's automatic stop never ends a newer recording",
      c5.state == "RECORDING" and sent(m5) == [], str(sent(m5)))
c5.stop()
cub.toggle()
check("after a stop the next loop starts on track 1 again", sent(m)[:2] == [(110, 0), (110, 127)])
m.log.clear()
cub.toggle()
check("...and its first recording sets a new loop length", sent(m)[:2] == [(106, 127), (106, 0)])
for _ in range(9):
    cub.toggle(); cub.hold(); cub.toggle()          # arm, record next track, play
check("the next track stops at track 8", cub.track == 7 and cub.state == "PLAYING")
cub.stop()
m.log.clear()
check("select_track(0..7) -> 0 then 127 on CC 110..117",
      all(cub.select_track(i) for i in range(8))
      and sent(m) == [(110 + i, v) for i in range(8) for v in (0, 127)])
m.log.clear()
check("out-of-range track ignored",
      not cub.select_track(8) and not cub.select_track(-1) and not cub.select_track("1")
      and sent(m) == [])
cub.select_track(4)
m.log.clear()
cub.toggle()
check("a chosen track (full window's menu) is where the first loop goes",
      sent(m)[:2] == [(114, 0), (114, 127)])
m.log.clear()
cub.cleanup()
first = sent(m)
m.log.clear()
cub.cleanup()
check("cleanup from RECORDING: record off + stop, once",
      first == [(102, 0), (104, 127), (104, 0)] and sent(m) == [] and cub.state == "IDLE",
      str(first))
check("no control port: toggles state, sends nothing",
      CubaseTransport(None).toggle() == "RECORDING")

# A note held when recording starts is sent again (main_cubase.py), so Cubase
# records it, not only its volume changes.
from types import SimpleNamespace

import main_cubase


class NoteLog:
    def __init__(self):
        self.log = []

    def send_note_on(self, note, velocity=64, channel=0):
        self.log.append(("on", note))

    def send_note_off(self, note, velocity=0, channel=0):
        self.log.append(("off", note))

    def resend_cc(self, control, channel=0):
        self.log.append(("cc", control))


main_cubase.RETRIGGER_DELAY_S = main_cubase.RETRIGGER_FROM_STOP_S = 0
main_cubase.COUNT_IN_S = 0
app = main_cubase.CubaseApp.__new__(main_cubase.CubaseApp)   # no camera, window or ports
app.cubase, app.midi_engine = CubaseTransport(None), NoteLog()
app.logic = SimpleNamespace(current_pitch_note=62)
app._prev_transport_state, app._retrigger_at = "IDLE", None
app._retrigger_held_note()
idle = list(app.midi_engine.log)
app.cubase.toggle()                                  # recording starts
app._retrigger_held_note()
app._retrigger_held_note()
check("held note re-sent once when recording starts: off, volume, on",
      idle == [] and app.midi_engine.log == [("off", 62), ("cc", 7), ("on", 62)],
      str(app.midi_engine.log))
app.midi_engine.log.clear()
app.cubase.toggle()                                  # recording stops: nothing re-sent
app._retrigger_held_note()
app.cubase.toggle(); app.cubase.hold()               # a 2-second fist starts a new layer
app.logic.current_pitch_note = -1                     # ... with no note held
app._retrigger_held_note()
check("nothing re-sent when recording stops, or when no note is held",
      app.midi_engine.log == [], str(app.midi_engine.log))
app.cubase.toggle(); app.cubase.toggle(); app.logic.current_pitch_note = 65
app._retrigger_held_note()
app.cubase.hold()
app._retrigger_held_note()
check("a 2-second fist re-sends the held note too",
      app.midi_engine.log == [("off", 65), ("cc", 7), ("on", 65)], str(app.midi_engine.log))
check("count-in off by default (as in this Cubase); 1 bar of 4/4 at 100 BPM would be 2.4 s",
      main_cubase.COUNT_IN_BARS == 0
      and 1 * main_cubase.COUNT_IN_BEATS_PER_BAR * 60 / 100 == 2.4)
main_cubase.COUNT_IN_S = 1000                         # a count-in that has not ended yet
app.cubase.stop(); app._retrigger_held_note(); app.midi_engine.log.clear()
app.cubase.toggle(); app._retrigger_held_note()      # first fist: from a stop
first = list(app.midi_engine.log)
app.cubase.toggle(); app._retrigger_held_note()
app.cubase.toggle(); app.cubase.hold(); app._retrigger_held_note()   # 2-second fist
check("the first fist waits for the count-in; a 2-second fist (no count-in) does not",
      first == [] and app.midi_engine.log == [("off", 65), ("cc", 7), ("on", 65)],
      str((first, app.midi_engine.log)))
main_cubase.COUNT_IN_S = 0

# Left-hand gestures through the logic, on a fake clock.
import src.logic_obb as logic_obb_module

real_time = logic_obb_module.time
clock = SimpleNamespace(now=1000.0)
logic_obb_module.time = SimpleNamespace(time=lambda: clock.now)
FIST, OPEN, THUMB = 2, 1, 0


def left_frames(lg, cls, n):
    for _ in range(n):
        lg.process(det_result([(box(0.25, 0.5), 0.9, cls)] if cls is not None else []))
        clock.now += 1 / 30


m = FakeMidi()
cub = CubaseTransport(m)
lg = HbbLogic(m, cub)
states = []
for _ in range(6):
    left_frames(lg, FIST, 1)
    states.append(cub.state)
check("left closedhand toggles CubaseTransport on the 5th frame",
      states == ["IDLE"] * 4 + ["RECORDING"] * 2, str(states))
left_frames(lg, OPEN, 3); clock.now += 2
left_frames(lg, FIST, 6)
left_frames(lg, FIST, 75)                            # keep that fist 2.5 s
check("fist -> PLAYING; holding that same fist records nothing new",
      cub.state == "PLAYING" and cub.track == 0)
left_frames(lg, OPEN, 3); clock.now += 2
left_frames(lg, FIST, 6)
check("a new fist while PLAYING keeps playing", cub.state == "PLAYING")
left_frames(lg, FIST, 65)
check("that fist held 2 s records track 2", cub.state == "RECORDING" and cub.track == 1)
left_frames(lg, OPEN, 3)
left_frames(lg, THUMB, 7)
check("thumb out shorter than 8 frames is ignored", cub.state == "RECORDING")
left_frames(lg, THUMB, 1)
check("thumb out held 8 frames stops: IDLE", cub.state == "IDLE")

m = FakeMidi()
cub = CubaseTransport(m)
lg = HbbLogic(m, cub)
left_frames(lg, FIST, 6)
left_frames(lg, None, 2); clock.now += 2             # left hand lost for 2 frames
left_frames(lg, FIST, 10)
check("a fist lost for 2 frames is the same fist: no second toggle", cub.state == "RECORDING")

looper = MidiLooper(FakeMidi(), channel=1)
lg = HbbLogic(FakeMidi(), looper)
left_frames(lg, THUMB, 12)
left_frames(lg, OPEN, 3); clock.now += 2
left_frames(lg, FIST, 6); left_frames(lg, FIST, 75)
check("in-app looper (main_obb.py): thumb out and long hold change nothing",
      looper.state == "RECORDING")
looper.cleanup()

# The same gestures through the YOLOv8 pose logic (main_cubase_lite.py --model v8),
# where fist and thumb out are read from the keypoints.
import src.logic as logic_module
from main_cubase_lite import POSE_STILL_FRAMES

logic_module.time = logic_obb_module.time


def pose_left_frames(lg, kpts_fn, n):
    for _ in range(n):
        hands = [(box(0.25, 0.5), 0.95, kpts_fn(0.25, 0.5))] if kpts_fn else []
        lg.process(pose_result(hands))
        clock.now += 1 / 30


m = FakeMidi()
cub = CubaseTransport(m)
lg = PoseLogic(m, cub)
lg._static_frames = POSE_STILL_FRAMES
pose_left_frames(lg, fist_kpts, 3)
s1 = cub.state
pose_left_frames(lg, open_hand_kpts, 3); clock.now += 2
pose_left_frames(lg, fist_kpts, 3)
s2 = cub.state
pose_left_frames(lg, open_hand_kpts, 3); clock.now += 2
pose_left_frames(lg, fist_kpts, 3)
pose_left_frames(lg, fist_kpts, 62)                  # the same, still fist kept 2 s
s3, t3 = cub.state, cub.track
pose_left_frames(lg, open_hand_kpts, 3)
pose_left_frames(lg, thumb_out_kpts, 7)
s4 = cub.state
pose_left_frames(lg, thumb_out_kpts, 1)
check("v8: fist, fist, fist kept 2 s, thumb out -> record, play, track 2, stop",
      (s1, s2, s3, t3, s4, cub.state) == ("RECORDING", "PLAYING", "RECORDING", 1, "RECORDING", "IDLE"),
      str((s1, s2, s3, t3, s4, cub.state)))

m = FakeMidi()
cub = CubaseTransport(m)
lg = PoseLogic(m, cub)
pose_left_frames(lg, fist_kpts, 3)
pose_left_frames(lg, None, 2); clock.now += 2         # no hands for 2 frames
pose_left_frames(lg, fist_kpts, 6)
check("v8: a fist lost for 2 frames is the same fist", cub.state == "RECORDING")

looper = MidiLooper(FakeMidi(), channel=1)
lg = PoseLogic(FakeMidi(), looper)
pose_left_frames(lg, thumb_out_kpts, 4)
check("v8 with the in-app looper (main.py): thumb out still counts as a fist, as before",
      looper.state == "RECORDING")
looper.cleanup()
logic_module.time = real_time
logic_obb_module.time = real_time

frame = np.zeros((480, 640, 3), np.uint8)
render_overlay(frame, HbbLogic(FakeMidi(), CubaseTransport(None)))
check("overlay renders with CubaseTransport", frame.any())


class FakePort:
    def __init__(self):
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)

    def close(self):
        pass


eng = MidiEngine(port="No Such Port 12345", dedupe_cc=(7,))
check("port= with a missing name opens nothing (no fallback)", eng.outport is None)
eng.outport = FakePort()
for v in (40, 40, 41, 41):
    eng.send_cc(7, v)
eng.send_cc(123, 0)
eng.send_cc(123, 0)
eng.reset_cc_cache()
eng.send_cc(7, 41)
eng2 = MidiEngine(port="No Such Port 12345", dedupe_cc=(7,))
eng2.outport = FakePort()
eng2.resend_cc(7)
eng2.send_cc(7, 90)
eng2.resend_cc(7)
check("resend_cc sends the last value again, and nothing before there is one",
      [(x.control, x.value) for x in eng2.outport.msgs] == [(7, 90), (7, 90)])

# Every note is preceded by its volume, even when the volume did not change
# (so a recorded loop does not play its first note at the previous pass's end).
eng3 = MidiEngine(port="No Such Port 12345", dedupe_cc=(7,))
eng3.outport = FakePort()
lg3 = HbbLogic(eng3, None)
lg3.process(det_result([(box(0.75, 0.5, 0.10, 0.15), 0.9, 1)]))   # seeds silence
lg3.process(det_result([(box(0.75, 0.3), 0.9, 1)]))               # note 1
lg3.process(det_result([(box(0.75, 0.7), 0.9, 1)]))               # note 2, same size/volume
msgs = [(x.type, getattr(x, "control", None)) for x in eng3.outport.msgs]
ons = [i for i, x in enumerate(msgs) if x[0] == "note_on"]
lg4 = HbbLogic(FakeMidi(), None)
lg4.min_note_s = 0.08
lg4.process(det_result([(box(0.75, 0.5, 0.10, 0.15), 0.9, 1)]))
lg4.process(det_result([(box(0.75, 0.3), 0.9, 1)]))               # a note
first = lg4.current_pitch_note
lg4.process(det_result([(box(0.75, 0.7), 0.9, 1)]))               # flicker right after
kept = lg4.current_pitch_note
import time as _t
_t.sleep(0.1)
lg4.process(det_result([(box(0.75, 0.7), 0.9, 1)]))
check("min_note_s: no pitch change before the note has lasted 0.08 s, then it changes",
      kept == first and lg4.current_pitch_note not in (-1, first), f"{first} {kept} {lg4.current_pitch_note}")
check("min_note_s is 0 by default (other programs unchanged)", HbbLogic(FakeMidi(), None).min_note_s == 0)
check("the volume goes right before every note, also when it is unchanged",
      len(ons) == 2 and all(msgs[i - 1] == ("control_change", 7) for i in ons), str(msgs))
check("dedupe_cc drops repeated CC7 only; reset resends",
      [(x.control, x.value) for x in eng.outport.msgs]
      == [(7, 40), (7, 41), (123, 0), (123, 0), (7, 41)])

# --------------------------------------------------------------------------
print("7. src/ui_lite.py settings  (light Cubase version: main_cubase_lite.py)")
from main_cubase_lite import CubaseLiteApp
from src.ui_lite import DEFAULT_ROOT, DEFAULT_SCALE, lite_settings

m = FakeMidi()
lg = HbbLogic(m, None)
app = CubaseLiteApp.__new__(CubaseLiteApp)   # no camera, window or ports
app.logic, app.midi_engine, app._current_program = lg, m, None
settings = lite_settings(DEFAULT_SCALE, DEFAULT_ROOT)
app.update_settings(settings)
check("starts on D minor, 2 octaves D4-D6 (15 notes)",
      lg.scale == [62, 64, 65, 67, 69, 70, 72, 74, 76, 77, 79, 81, 82, 84, 86], str(lg.scale))
app.update_settings(lite_settings(DEFAULT_SCALE, DEFAULT_ROOT, "1 octave"))
check("1 octave: D4-D5 (8 notes)", lg.scale == [62, 64, 65, 67, 69, 70, 72, 74], str(lg.scale))
app.update_settings(lite_settings("Theremin", DEFAULT_ROOT, "1 octave"))
check("theremin: no note added", lg.scale == [62, 64, 65, 67, 69, 70, 72, 74], str(lg.scale))
check("no Program Change (instruments are chosen in Cubase)",
      "instrument_program" not in settings and not [e for e in m.log if e[0] == "pc"])
from main_cubase_lite import MODELS
check("--model s / x / v8: the standard, the heaviest and the YOLOv8 hand-pose model",
      MODELS["s"][:2] == ("hbb-s-fold1-320.mlpackage", 320)
      and MODELS["x"][:2] == ("hbb-x-fold0-416.mlpackage", 416)
      and MODELS["v8"][0] == "yolov8n-hand-pose.mlpackage" and MODELS["v8"][3] == "pose")
check("fixed sound settings match the full window's defaults",
      lg.volume_gain == 2.0 and lg.volume_gate == 8 and lg.show_pitch and not lg.show_borderlines)

print()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
