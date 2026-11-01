"""Light Cubase version: main_cubase.py with a smaller, faster window.

Same detector, gestures, buses and left-fist record -> play -> stop in Cubase.
The window has the camera picture at the camera's own size, Scale and Root
Note menus (starting on D minor), a 1 / 2 octave Range switch and a Calibrate
button. Each range ends on the root (D4-D5, D4-D6). Instruments
and tracks are chosen in Cubase, and no Program Change is sent. See
src/ui_lite.py.

Three gesture models, everything else identical:
  s   hbb-s-fold1-320     the standard model (default)
  x   hbb-x-fold0-416     the heaviest; the most accurate YOLO26 model of the
                          research study on its held-out test photos
  v8  yolov8n-hand-pose   the first working version's model (main.py): 21
                          keypoints per hand, gestures read from the keypoints
                          by src/logic.py. Exported to Core ML like the other
                          two (17 ms per frame; PyTorch on the GPU took 61)

    Run:  uv run python main_cubase_lite.py
          uv run python main_cubase_lite.py --model x
          uv run python main_cubase_lite.py --model v8
"""
import argparse

from main_cubase import CubaseApp
from src.logic import GestureLogic as PoseLogic
from src.ui_lite import LiteUI
from src.vision_hbb import HbbVision

# Model files in the project folder: choice -> (file, input size, label, task).
MODELS = {
    "s": ("hbb-s-fold1-320.mlpackage", 320, "hbb-s @ 320 px", "detect"),
    "x": ("hbb-x-fold0-416.mlpackage", 416, "hbb-x @ 416 px", "detect"),
    "v8": ("yolov8n-hand-pose.mlpackage", 384, "YOLOv8n hand-pose @ 384 px", "pose"),
}

# The pose logic mutes a box that stays still for this many frames (its guard
# against walls and picture frames that look like hands). main.py ran at 20 fps
# with 30 frames (1.5 s); here the loop runs at the camera's 30 fps, and a fist
# is held still for 2 s to record the next track, so allow 3 s.
POSE_STILL_FRAMES = 90


class CubaseLiteApp(CubaseApp):
    def __init__(self, model="s"):
        self.model_file, self.model_imgsz, self.model_label, self.model_task = MODELS[model]
        self._infer_ms = []
        super().__init__()

    def _make_logic(self):
        if self.model_task != "pose":
            return super()._make_logic()
        logic = PoseLogic(self.midi_engine, self.cubase)
        logic._static_frames = POSE_STILL_FRAMES
        return logic

    def _make_vision(self):
        return HbbVision(model=self.model_file, imgsz=self.model_imgsz, task=self.model_task)

    def _make_ui(self):
        return LiteUI(self.update_settings, self.on_calibrate, model_name=self.model_label)

    def update_ui_video(self):
        # Average the model's time per frame and show it about once a second.
        ms = getattr(self.vision, "last_infer_ms", None)
        if ms is not None:
            self._infer_ms.append(ms)
            if len(self._infer_ms) >= 25:
                self.ui.set_detection_time(sum(self._infer_ms) / len(self._infer_ms))
                self._infer_ms = []
        idle = self.cubase.state == self.cubase.IDLE
        self.ui.set_loop_track(None if idle else self.cubase.track + 1)
        super().update_ui_video()

    def update_settings(self, settings):
        super().update_settings(settings)
        # ScaleGenerator stops one step below the next root (D4-C5 for one
        # octave of D minor); add that root so the range ends on it (D4-D5).
        octaves = settings.get("octaves")
        if octaves and settings["scale_type"] != "Theremin" and self.logic.scale:
            top = self.logic.scale[0] + 12 * octaves
            if top <= 127:
                self.logic.scale = self.logic.scale + [top]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Light Cubase version of the gesture instrument.")
    parser.add_argument("--model", choices=sorted(MODELS), default="s",
                        help="s: standard (default); x: heaviest, most accurate; "
                             "v8: the first version's YOLOv8 hand-pose model")
    app = CubaseLiteApp(model=parser.parse_args().model)
    app.run()
