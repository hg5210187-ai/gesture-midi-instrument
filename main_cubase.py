"""Cubase version: the gesture instrument playing Cubase LE / AI / Elements 13.

Same detector and gestures as main_obb.py (src/vision_hbb.py with
hbb-s-fold1-320, src/logic_obb.py), with three differences:

  * the left hand records loops in Cubase instead of the in-app looper, over
    Cubase's cycle range: fist = record -> play, fist held 2 s = record the
    next track, thumb out = stop (src/cubase_control.py);
  * the Cubase Track menu selects which Cubase track the right hand plays;
  * the Instrument menu switches HALion Sonic sounds (GM Mode on).

Notes go to IAC Driver Bus 1, control messages to IAC Driver Bus 2, where the
MIDI Remote script in cubase/midi_remote/ receives them. Setup checklist:
README.md, "Cubase version".

    Run:  uv run python main_cubase.py
"""
import os
import threading
import time
import queue
from src.vision_hbb import HbbVision
from src.midi_engine import MidiEngine
from src.logic_obb import GestureLogic
from src import cubase_control
from src.cubase_control import CubaseTransport
from src.ui import SettingsUI
from src.scales import ScaleGenerator
from src.overlay import render_overlay

# Cubase records only notes that start while it records. A note already held
# when recording starts is sent again this long after the record command: a
# punch-in while playing (2-second fist) starts at once; from a stop (first
# fist) Cubase takes a moment to start the transport. Cubase's MIDI record
# catch range (100 ms) moves a note that arrives just before recording starts
# to its start, so these can be a little early rather than late.
RETRIGGER_DELAY_S = 0.15
RETRIGGER_FROM_STOP_S = 0.2

# Cubase's count-in, if it is on: it plays when recording starts from a stop
# (the first fist), and the re-send waits for it. Off by default, as in the
# Cubase this was set up with. To match a count-in: CUBASE_COUNT_IN_BARS (Metronome
# Setup "Number of Bars in Count-In"), CUBASE_COUNT_IN_BEATS (its beats per bar)
# and CUBASE_TEMPO (the project tempo).
# Shortest note: a one-frame detection flicker otherwise makes notes of a few
# hundredths of a second, and Cubase sometimes lost their ends, leaving a note
# that rang under the rest of the recording.
MIN_NOTE_S = 0.08

TEMPO_BPM = float(os.environ.get("CUBASE_TEMPO", 120))
COUNT_IN_BARS = float(os.environ.get("CUBASE_COUNT_IN_BARS", 0))
COUNT_IN_BEATS_PER_BAR = float(os.environ.get("CUBASE_COUNT_IN_BEATS", 4))
COUNT_IN_S = COUNT_IN_BARS * COUNT_IN_BEATS_PER_BAR * 60.0 / TEMPO_BPM

NOTES_PORT = os.environ.get("CUBASE_NOTES_PORT", "IAC Driver Bus 1")
CONTROL_PORT = os.environ.get("CUBASE_CONTROL_PORT", "IAC Driver Bus 2")


class CubaseApp:
    def __init__(self):
        # Notes and control messages on separate buses. CC7 (volume) is sent
        # only when it changes, so Cubase recordings aren't flooded with it.
        self.midi_engine = MidiEngine(port=NOTES_PORT, dedupe_cc=(7,))
        self.control_engine = MidiEngine(port=CONTROL_PORT)
        if self.control_engine.outport is None:
            print(f"⚠️ No '{CONTROL_PORT}': the fist and Cubase Track menu are off. "
                  "Add the port in Audio MIDI Setup → IAC Driver (README, 'Cubase version').")
        self.cubase = CubaseTransport(self.control_engine)
        # The transport stands in for the looper: GestureLogic toggles it on a
        # sustained left fist, and the overlay/UI show its state.
        self.logic = self._make_logic()
        self.logic.min_note_s = MIN_NOTE_S
        self.vision = self._make_vision()
        self.running = True

        # MIDI_LATENCY_DEBUG=1 prints the vision loop's rate and gesture->MIDI
        # timings every few seconds (see vision_loop).
        self.latency_debug = os.environ.get("MIDI_LATENCY_DEBUG") == "1"

        # Last MIDI program (instrument) sent, so we only emit a Program Change
        # when the selection actually changes rather than on every settings tweak.
        self._current_program = None

        # Cubase Track chosen in the UI, applied by the vision thread before its
        # next frame so all note traffic stays on one thread.
        self._pending_track = None

        # Re-sending a held note when recording starts (see _retrigger_held_note).
        self._prev_transport_state = self.cubase.state
        self._retrigger_at = None

        # Thread-safe queue for UI image updates
        self.frame_queue = queue.Queue(maxsize=2)

        # UI (Settings Window)
        self.ui = self._make_ui()

        # Processing thread
        self.process_thread = threading.Thread(target=self.vision_loop, daemon=True)

    def _make_logic(self):
        """Gestures -> MIDI; main_cubase_lite.py --model v8 uses the pose logic."""
        return GestureLogic(self.midi_engine, self.cubase)

    def _make_vision(self):
        """The camera + gesture model; main_cubase_lite.py can choose the model."""
        return HbbVision()

    def _make_ui(self):
        """The window; main_cubase_lite.py swaps in the light one."""
        return SettingsUI(self.update_settings, self.on_calibrate,
                          cubase_mode=True, on_cubase_track=self.on_cubase_track)

    def update_settings(self, settings):
        """Callback from UI to update engine logic."""
        print(f"Updating settings: {settings}")

        # Volume sensitivity + gate + overlay toggles (read by the vision thread)
        self.logic.volume_gain = settings.get("volume_gain", self.logic.volume_gain)
        self.logic.volume_gate = settings.get("volume_gate", self.logic.volume_gate)
        self.logic.show_borderlines = settings.get("show_borderlines", False)
        self.logic.show_pitch = settings.get("show_pitch", False)

        # Instrument (MIDI Program Change), only on an actual change. Cubase
        # passes it to the selected track; HALion Sonic follows it in GM Mode.
        program = settings.get("instrument_program")
        if program is not None and program != self._current_program:
            self.midi_engine.send_program_change(program, channel=0)
            self._current_program = program
            print(f"Instrument changed -> program {program}")

        # Update scale
        raw_scale_type = settings["scale_type"]
        scale_type = raw_scale_type.lower().replace(" ", "_")

        self.logic.scale_type = scale_type

        range_preset = settings.get("range_preset", "Full Range (5 Octaves)")
        if range_preset == "Melody (2 Octaves)":
            start_octave = 4
            num_octaves = 2
        elif range_preset == "Melody (1 Octave)":
            start_octave = 4
            num_octaves = 1
        elif "Bass" in range_preset:
            start_octave = 2
            num_octaves = 1
        else:
            start_octave = 2
            num_octaves = 5

        if scale_type != "theremin":
            new_scale = ScaleGenerator.get_scale(settings["root_note"], scale_type, start_octave=start_octave, num_octaves=num_octaves)
            self.logic.scale = new_scale
            print(f"Scale updated to {settings['root_note']} {scale_type} ({num_octaves} octaves)")
        else:
            print("Theremin mode active: Continuous pitch tracking.")

    def on_cubase_track(self, index):
        """UI 'Cubase Track' menu (Tk thread): queue the switch for the vision thread."""
        self._pending_track = index

    def _apply_pending_track(self):
        index, self._pending_track = self._pending_track, None
        if index is None:
            return
        # Release the sounding note on the old track first, so it can't hang
        # there; the next frame re-triggers it on the new track.
        self.logic._silence_right_hand()
        self.midi_engine.send_cc(123, 0)       # All Notes Off
        self.midi_engine.reset_cc_cache()      # resend volume to the new track
        if self.cubase.select_track(index):
            print(f"Cubase track -> {index + 1}")

    def _retrigger_held_note(self):
        """Vision thread, after each frame. When the transport has just started
        recording (first fist or a 2-second fist), send the note the right
        hand is holding again, after its volume, RETRIGGER_DELAY_S after
        recording really starts (after the count-in, for the first fist), so
        the recording has it. Otherwise Cubase would record only the volume
        changes of a note that started before recording did."""
        state = self.cubase.state
        if state != self._prev_transport_state:
            from_stop = self._prev_transport_state == self.cubase.IDLE
            self._prev_transport_state = state
            # A 2-second fist switches record on LAYER_RECORD_DELAY_S after the
            # jump to the loop's start, so the re-send waits for that too.
            delay = ((RETRIGGER_FROM_STOP_S + COUNT_IN_S) if from_stop
                     else cubase_control.LAYER_RECORD_DELAY_S + RETRIGGER_DELAY_S)
            self._retrigger_at = (time.perf_counter() + delay
                                  if state == self.cubase.RECORDING else None)
        if self._retrigger_at is None or time.perf_counter() < self._retrigger_at:
            return
        self._retrigger_at = None
        note = self.logic.current_pitch_note
        if note != -1:
            self.midi_engine.send_note_off(note)
            self.midi_engine.resend_cc(7)
            self.midi_engine.send_note_on(note)
            self.logic._note_on_time = time.time()   # counts as a new note

    def on_calibrate(self):
        """UI 'Calibrate Min' button: capture the current right-hand box area."""
        area = self.logic.calibrate_min()
        if area is not None:
            self.ui.set_calib_status(f"Calibrated (min area = {area:.4f})", ok=True)
        else:
            self.ui.set_calib_status("No right hand detected - try again", ok=False)

    def vision_loop(self):
        """Camera processing and MIDI logic."""
        print("Vision loop started.")
        # No pacing here: get_frame() blocks until the camera delivers a new
        # frame, so the loop runs at camera rate (lowest latency) without
        # spinning a core. A single bad frame is dropped; we only give up after
        # errors persist, and cleanup() runs once on genuine loop exit.
        consecutive_errors = 0
        try:
            while self.running:
                try:
                    success, frame, result = self.vision.get_frame()
                    if not success:
                        print("Vision loop: Failed to get frame.")
                        time.sleep(0.1)
                        continue

                    self._apply_pending_track()

                    # Process gestures and send MIDI
                    self.logic.process(result)
                    self._retrigger_held_note()
                    if self.latency_debug:
                        self._log_latency()

                    render_overlay(frame, self.logic)

                    # Put frame into the queue (drop oldest if full to avoid lag)
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)

                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    print(f"Vision loop: dropping frame after error "
                          f"({consecutive_errors}): {e}")
                    if consecutive_errors >= 60:
                        print("Vision loop: too many consecutive errors; stopping.")
                        break
                    time.sleep(0.05)
        finally:
            self.cleanup()

    def _log_latency(self, every=5.0):
        """Collect per-frame timings; print mean/max every ``every`` seconds.

        "frame age at MIDI" is camera frame delivered -> MIDI sent. It excludes
        the camera's own internal delay, which can't be observed from here.
        """
        now = time.perf_counter()
        if not hasattr(self, "_lat_ages"):
            self._lat_ages, self._lat_infer, self._lat_since = [], [], now
        self._lat_ages.append((now - self.vision.last_capture_ts) * 1000.0)
        self._lat_infer.append(self.vision.last_infer_ms)
        elapsed = now - self._lat_since
        if elapsed >= every:
            n = len(self._lat_ages)
            print(f"[latency] {n / elapsed:.1f} fps | "
                  f"inference mean {sum(self._lat_infer) / n:.1f} ms, "
                  f"max {max(self._lat_infer):.1f} ms | "
                  f"frame age at MIDI mean {sum(self._lat_ages) / n:.1f} ms, "
                  f"max {max(self._lat_ages):.1f} ms")
            self._lat_ages, self._lat_infer, self._lat_since = [], [], now

    def update_ui_video(self):
        """Runs in the main thread to safely update Tkinter."""
        if not self.frame_queue.empty():
            frame = self.frame_queue.get()
            self.ui.update_image(frame)

        # Cubase transport status (as last set by the fist)
        self.ui.update_looper_status(self.cubase.state)

        if self.running:
            # Display only (~25 FPS); gesture->MIDI runs at camera rate.
            self.ui.after(40, self.update_ui_video)

    def cleanup(self):
        # Runs twice (vision thread exit + after the UI closes); each step is
        # safe to repeat, and the transport sends Stop only the first time.
        self.running = False
        self.cubase.cleanup()
        self.vision.release()
        self.midi_engine.close()
        self.control_engine.close()

    def run(self):
        self.process_thread.start()
        # Start UI update polling
        self.ui.after(100, self.update_ui_video)
        # Main thread runs the settings UI
        self.ui.mainloop()
        # Let the vision thread finish its current frame before tearing down;
        # exiting the interpreter while it is mid-inference crashes torch.
        self.running = False
        self.process_thread.join(timeout=3)
        self.cleanup()


if __name__ == "__main__":
    app = CubaseApp()
    app.run()
