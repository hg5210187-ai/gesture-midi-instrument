"""Cubase control for main_cubase.py and main_cubase_lite.py.

The left hand drives Cubase's transport instead of the in-app looper, and the
app selects which Cubase track is recorded and played. Everything is sent as
Control Change on MIDI channel 16 to a second IAC bus, where the MIDI Remote
script cubase/midi_remote/indigo/gestureinstrument/Indigo_GestureInstrument.js
turns it into Cubase actions. The CC numbers below must match that script.
"""
import threading
import time

CONTROL_CHANNEL = 15          # MIDI channel 16 (mido counts from 0)
CC_RECORD = 102               # value: 127 = record on, 0 = record off
CC_CYCLE = 103                # value: 127 = cycle on, 0 = cycle off
CC_STOP = 104                 # command: fires on 127, re-armed by 0
CC_GOTO_LEFT_LOCATOR = 105    # command: fires on 127, re-armed by 0
CC_SET_RIGHT_LOCATOR = 106    # command: right locator to the playhead
CC_SELECT_TRACK = 110         # 110-117 select tracks 1-8
NUM_TRACKS = 8

# Pause between selecting a track and switching record on, so Cubase has armed
# the newly selected track ("Enable Record on Selected MIDI Track") first.
SELECT_SETTLE_S = 0.05

# Pause between cycle off and starting the first recording. Sent together with
# the jump and record on, Cubase ignored the cycle off (seen in a screen
# recording): the first recording ran inside the previous loop's cycle and,
# played past its end, wrapped and recorded over its own start.
CYCLE_OFF_SETTLE_S = 0.15

# Pause between stopping the first recording and starting the loop (cycle on,
# back to the left locator). Sent together with the record-off, Cubase dropped
# them while it finished the recording, and kept playing past the loop.
LOOP_START_DELAY_S = 0.2

# A new layer stops recording by itself just after one pass of the loop: this
# long after the loop comes round again. Cubase's MIDI Cycle Record Mode must be
# "Keep Last": it keeps the last complete pass and discards the unfinished one,
# so the layer is exactly one loop long, with no gap at its end. (Stopping just
# before the end, as first done, left a gap of about 0.2 s; with "Mix", a stop
# after the end records the start of the second pass on top of the first.) The
# loop length is measured from the first recording's record command to the fist
# that closed it, which includes Cubase's start-up (about 0.15 s), so the stop
# comes about 0.45 s into the second pass.
LAYER_STOP_AFTER_S = 0.3

# A new layer jumps to the loop's start and switches record on this much
# later. Sent together, Cubase started recording before it moved, so the layer
# was recorded from wherever the loop was when the fist was held.
LAYER_RECORD_DELAY_S = 0.15


class _NoSender:
    """Stands in for a missing control port, so the app still runs."""

    def send_cc(self, control, value, channel=0):
        pass


class CubaseTransport:
    """Drop-in for MidiLooper whose loops are recorded and played by Cubase.

    It has MidiLooper's three states and toggle(), so GestureLogic, the
    overlay badge and the UI status label work unchanged, plus hold() and
    stop(), which GestureLogic calls only on a looper that has them:

        fist        IDLE -> RECORDING      select the start track (track 1
                                           unless the app chose another),
                                           cycle off, go to the left locator,
                                           record on (from a stop, so Cubase's
                                           count-in plays first, if it is on)
        fist        RECORDING -> PLAYING   first recording: right locator to
                                           the playhead, record off, and 0.2 s
                                           later cycle on and back to the left
                                           locator, so the loop is exactly
                                           what was recorded. Later ones:
                                           record off; the transport keeps
                                           cycling
        fist        PLAYING                nothing (arms hold())
        fist held   PLAYING -> RECORDING   select the next track, cycle on (again),
                    2 s                    back to the left locator, and 0.15 s
                                           later record: the new loop lies on
                                           top of the first,
                                           from its start, and the earlier
                                           loops play from the start with it.
                                           Recording stops by itself just after
                                           one pass (or earlier, with a fist);
                                           with Cubase's MIDI Cycle Record Mode
                                           on Keep Last, exactly one pass is kept
        thumb out   any -> IDLE            record off if recording, stop

    Loops therefore go on tracks 1, 2, 3 ... (instrument, sampler and MIDI
    tracks in MixConsole order); after track 8 it stays on track 8. The first
    recording starts at the left locator and its length (time between the two
    fists) becomes the cycle range. Values are absolute (never toggles): if
    Cubase is changed by hand, only this object's state label goes stale; no
    gesture can invert a command.
    """

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    PLAYING = "PLAYING"

    def __init__(self, sender=None):
        # ``sender`` is anything with send_cc (a MidiEngine on the control bus).
        self.midi = sender if sender is not None else _NoSender()
        self.state = self.IDLE
        self.start_track = 0      # where the first loop goes (0 = track 1)
        self.track = 0            # the track being recorded or last recorded
        # Set by a fist that starts while PLAYING; only such a fist may hold().
        self._hold_armed = False
        # False until the first recording has set the cycle (the loop length).
        self._loop_set = False
        # Loop length in seconds, measured on the first recording, and a count
        # of recordings, so a layer's automatic stop only ends its own one.
        self.loop_s = None
        self._rec_start = None
        self._take = 0
        # rtmidi output is not locked, and the vision thread and the main
        # thread (cleanup) both send; keep each message sequence whole.
        self._lock = threading.Lock()

    @property
    def label(self):
        """Overlay badge text: which track the loops are on."""
        return "CUBASE" if self.state == self.IDLE else f"CUBASE T{self.track + 1}"

    def toggle(self):
        """A confirmed fist. Returns the new state."""
        with self._lock:
            if self.state == self.IDLE:
                self.track = self.start_track
                self._select(self.track)
                time.sleep(SELECT_SETTLE_S)
                # Cycle off, so the first recording can be any length.
                self._switch_off(CC_CYCLE)
                time.sleep(CYCLE_OFF_SETTLE_S)
                self._command(CC_GOTO_LEFT_LOCATOR)
                self._switch_on(CC_RECORD)
                self._rec_start = time.monotonic()
                self._take += 1
                self.state = self.RECORDING
                self._hold_armed = False
                self._loop_set = False
                self.loop_s = None
            elif self.state == self.RECORDING:
                # PLAYING before the loop start is scheduled: it only runs if
                # the state is still PLAYING when it fires.
                self.state = self.PLAYING
                self._hold_armed = False
                if not self._loop_set:
                    # The loop ends here: right locator first, at this moment.
                    self.loop_s = time.monotonic() - self._rec_start
                    self._command(CC_SET_RIGHT_LOCATOR)
                    self._cc(CC_RECORD, 0)
                    self._later(LOOP_START_DELAY_S, self._start_loop_locked)
                    self._loop_set = True
                else:
                    self._cc(CC_RECORD, 0)
            else:
                # PLAYING: a short fist does nothing; held for 2 s it calls hold().
                self._hold_armed = True
            return self.state

    def hold(self):
        """A fist held 2 s. From PLAYING, if that fist started while PLAYING:
        record on the next track. Returns the new state."""
        with self._lock:
            if self.state == self.PLAYING and self._hold_armed:
                self.track = min(self.track + 1, NUM_TRACKS - 1)
                self._select(self.track)
                time.sleep(SELECT_SETTLE_S)
                # Cycle on again in case it was lost, and record from the loop's
                # start so the new part lies exactly on top of the first.
                self._switch_on(CC_CYCLE)
                self._command(CC_GOTO_LEFT_LOCATOR)
                # RECORDING (and the new take) before record on is scheduled: it
                # only runs if this recording is still on when it fires.
                self.state = self.RECORDING
                self._take += 1
                take = self._take
                self._later(LAYER_RECORD_DELAY_S, lambda: self._layer_record_on_locked(take))
                if self.loop_s is not None:
                    # Timed from the jump, so the stop falls just after the
                    # loop comes round (see LAYER_STOP_AFTER_S).
                    self._later(self.loop_s + LAYER_STOP_AFTER_S,
                                lambda: self._end_layer_locked(take))
            self._hold_armed = False
            return self.state

    def stop(self):
        """A confirmed left thumbout: stop recording and playing. Returns IDLE."""
        with self._lock:
            self._stop_locked()
            return self.state

    def record_event(self, *args, **kwargs):
        """Cubase records the notes itself; nothing to keep here."""

    def select_track(self, index):
        """Select Cubase track ``index`` (0-7, in MixConsole order) and make it
        where the next loop goes. Returns False and sends nothing for any other
        value."""
        if not isinstance(index, int) or not 0 <= index < NUM_TRACKS:
            return False
        with self._lock:
            self._select(index)
            self.start_track = self.track = index
        return True

    def cleanup(self):
        """Stop Cubase if it was left recording or playing. Safe to call more
        than once: from IDLE it sends nothing."""
        with self._lock:
            self._stop_locked()

    # --- Private ---

    def _stop_locked(self):
        if self.state == self.RECORDING:
            self._cc(CC_RECORD, 0)
        if self.state != self.IDLE:
            self._command(CC_STOP)
        self.state = self.IDLE
        self._hold_armed = False
        self._loop_set = False

    def _later(self, delay, body):
        """Run ``body`` (which expects the lock held) after ``delay`` seconds
        on a timer thread, or at once if ``delay`` is 0. Called with the lock
        held."""
        if delay <= 0:
            body()
            return

        def run():
            with self._lock:
                body()

        timer = threading.Timer(delay, run)
        timer.daemon = True
        timer.start()

    def _layer_record_on_locked(self, take):
        # Record on once Cubase is back at the loop's start, unless this layer
        # was already ended (a fist, a thumb out) or another recording began.
        if self.state == self.RECORDING and self._take == take:
            self._switch_on(CC_RECORD)

    def _end_layer_locked(self, take):
        # One pass recorded: stop, unless this recording already ended (a fist,
        # a thumb out) or another one has started since.
        if self.state == self.RECORDING and self._take == take:
            self._cc(CC_RECORD, 0)
            self.state = self.PLAYING
            self._hold_armed = False

    def _start_loop_locked(self):
        # Skipped if a thumb out or cleanup stopped everything in the meantime.
        if self.state == self.PLAYING:
            self._switch_on(CC_CYCLE)
            self._command(CC_GOTO_LEFT_LOCATOR)

    def _select(self, index):
        self._switch_on(CC_SELECT_TRACK + index)

    def _cc(self, control, value):
        self.midi.send_cc(control, value, channel=CONTROL_CHANNEL)

    def _switch_on(self, control):
        # 0 first, so the 127 is a change even if the script's copy of this
        # value was left at 127 (e.g. Cubase was stopped by hand).
        self._cc(control, 0)
        self._cc(control, 127)

    def _switch_off(self, control):
        # 127 first, so the 0 is a change even if the script's copy was 0.
        self._cc(control, 127)
        self._cc(control, 0)

    def _command(self, control):
        # Command bindings fire on the press; the 0 releases the button.
        self._cc(control, 127)
        self._cc(control, 0)
