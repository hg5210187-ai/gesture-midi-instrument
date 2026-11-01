"""Light window for main_cubase_lite.py: the camera picture and four controls.

Only Scale, Root Note, Range (1 or 2 octaves) and Calibrate can be changed.
The rest is fixed at the full window's defaults: volume sensitivity 2.0,
volume gate 8, current pitch shown. There is no Instrument menu, so no
Program Change is ever sent and the sound is whatever is loaded on the Cubase
track; tracks are chosen by clicking them in Cubase. The gesture model in use
and its average detection time are shown under the controls.

The picture is drawn at the camera's own size into one Tk PhotoImage that is
reused for every frame. The full window (src/ui.py) builds a new CTkImage
scaled to the panel for each frame: 95 ms per redraw on a maximised window,
which is redrawn every 40 ms, so its menus stopped responding. This way takes
about 30 ms.
"""
import tkinter as tk

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from src.ui import NOTES, SCALE_OPTIONS

PREVIEW_SIZE = (640, 480)      # the camera's own frame size, so no scaling
DEFAULT_SCALE = "Minor"
DEFAULT_ROOT = "D"

# Range switch -> (the full window's range preset, number of octaves).
RANGES = {"1 octave": ("Melody (1 Octave)", 1), "2 octaves": ("Melody (2 Octaves)", 2)}
DEFAULT_RANGE = "2 octaves"

# Settings the full window has controls for, fixed at its defaults.
FIXED_SETTINGS = {
    "volume_gain": 2.0,
    "volume_gate": 8,
    "show_borderlines": False,
    "show_pitch": True,
}


def lite_settings(scale_type, root_note, range_name=DEFAULT_RANGE):
    """The settings dict for CubaseApp.update_settings (no instrument_program).

    ``octaves`` is read only by CubaseLiteApp.update_settings.
    """
    preset, octaves = RANGES[range_name]
    return dict(FIXED_SETTINGS, scale_type=scale_type, root_note=root_note,
                range_preset=preset, octaves=octaves)


class LiteUI(ctk.CTk):
    def __init__(self, on_change_callback, on_calibrate=None, model_name=None):
        super().__init__()
        self.title(f"Gesture Instrument  ·  {model_name}" if model_name else "Gesture Instrument")
        self.on_change_callback = on_change_callback
        self.on_calibrate = on_calibrate
        self._shown_state = None

        controls = ctk.CTkFrame(self)
        controls.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ns")

        ctk.CTkLabel(controls, text="Scale", font=("Arial", 16, "bold")).pack(
            padx=15, pady=(15, 5), anchor="w")
        self.scale_type = ctk.CTkOptionMenu(controls, values=SCALE_OPTIONS,
                                            command=self._update_settings)
        self.scale_type.set(DEFAULT_SCALE)
        self.scale_type.pack(padx=15, pady=(0, 10), fill="x")

        ctk.CTkLabel(controls, text="Root Note", font=("Arial", 16, "bold")).pack(
            padx=15, pady=(10, 5), anchor="w")
        self.root_note = ctk.CTkOptionMenu(controls, values=NOTES,
                                           command=self._update_settings)
        self.root_note.set(DEFAULT_ROOT)
        self.root_note.pack(padx=15, pady=(0, 10), fill="x")

        ctk.CTkLabel(controls, text="Range", font=("Arial", 16, "bold")).pack(
            padx=15, pady=(10, 5), anchor="w")
        self.range_name = ctk.CTkSegmentedButton(controls, values=list(RANGES),
                                                 command=self._update_settings)
        self.range_name.set(DEFAULT_RANGE)
        self.range_name.pack(padx=15, pady=(0, 10), fill="x")

        self.calibrate_btn = ctk.CTkButton(controls, text="Calibrate",
                                           command=self._calibrate)
        self.calibrate_btn.pack(padx=15, pady=(10, 5), fill="x")
        self.calib_status = ctk.CTkLabel(
            controls, text="Hold the right hand where it should\nbe silent, then calibrate",
            font=("Arial", 11), text_color="gray60", justify="left")
        self.calib_status.pack(padx=15, pady=(0, 10), anchor="w")

        self.looper_label = ctk.CTkLabel(controls, text="Cubase: Idle",
                                         font=("Arial", 14, "bold"), text_color="gray")
        self.looper_label.pack(padx=15, pady=(20, 0))
        self.track_label = ctk.CTkLabel(controls, text="", font=("Arial", 12))
        self.track_label.pack(padx=15, pady=(0, 5))
        self._shown_track = None
        ctk.CTkLabel(controls, text="Left hand\nfist: record → play\nhold fist 2 s: record one loop on the next track\nthumb out: stop",
                     font=("Arial", 11), text_color="gray60", justify="left").pack(
            padx=15, pady=(0, 15), anchor="w")

        if model_name:
            ctk.CTkLabel(controls, text=f"Model: {model_name}",
                         font=("Arial", 12, "bold")).pack(padx=15, pady=(10, 0), anchor="w")
            self.detect_label = ctk.CTkLabel(controls, text="Detection: – ms per frame",
                                             font=("Arial", 12), text_color="gray60")
            self.detect_label.pack(padx=15, pady=(0, 15), anchor="w")

        # Plain Tk label holding one PhotoImage; update_image pastes into it.
        self._photo = ImageTk.PhotoImage(Image.new("RGB", PREVIEW_SIZE))
        self.video_label = tk.Label(self, image=self._photo, bg="black",
                                    bd=0, highlightthickness=0)
        self.video_label.grid(row=0, column=1, padx=(5, 10), pady=10)

        # CTk fixes the window size at creation; fit it to the content instead.
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")
        self.resizable(False, False)

        self._update_settings()   # start in D minor

    def update_image(self, cv_frame):
        """Show a BGR camera frame (called from the main thread)."""
        try:
            if (cv_frame.shape[1], cv_frame.shape[0]) != PREVIEW_SIZE:
                cv_frame = cv2.resize(cv_frame, PREVIEW_SIZE, interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
            self._photo.paste(Image.fromarray(rgb))
        except Exception as e:
            print(f"UI Update Error: {e}")

    def update_looper_status(self, state):
        """Show the Cubase transport state; only redraws when it changes."""
        if state == self._shown_state:
            return
        self._shown_state = state
        colors = {"IDLE": "gray", "RECORDING": "red", "PLAYING": "green"}
        self.looper_label.configure(text=f"Cubase: {state.capitalize()}",
                                    text_color=colors.get(state, "gray"))

    def set_loop_track(self, number):
        """Show which Cubase track the loop is on (1-8), or nothing when idle."""
        if number == self._shown_track:
            return
        self._shown_track = number
        self.track_label.configure(text=f"on track {number}" if number else "")

    def set_detection_time(self, ms):
        """Show the model's average time per frame (main thread)."""
        if hasattr(self, "detect_label"):
            self.detect_label.configure(text=f"Detection: {ms:.0f} ms per frame")

    def set_calib_status(self, text, ok=True):
        self.calib_status.configure(text=text, text_color="green" if ok else "orange")

    def _update_settings(self, _=None):
        # Cheap (a scale rebuild, no MIDI), so it runs here on the Tk thread.
        self.on_change_callback(lite_settings(self.scale_type.get(), self.root_note.get(),
                                              self.range_name.get()))

    def _calibrate(self):
        if self.on_calibrate:
            self.on_calibrate()
