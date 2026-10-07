# Models

No model weights are stored in this repository. `.gitignore` excludes `*.pt`, `*.mlpackage`,
`*.task` and `*.onnx`. Model files go in the **project root**. Three of the programs find
that folder themselves; `main.py` looks in the current directory, so start it from the root.

| Program | File it loads | What the file is | Where it comes from |
|---|---|---|---|
| `main_mediapipe.py` | `hand_landmarker.task` | MediaPipe HandLandmarker bundle, 7.8 MB | Public download from Google, below |
| `main.py` | `yolov8n-hand-pose.pt` | YOLOv8n pose model, one class `hand`, 21 keypoints, 7 MB | A third-party checkpoint, not redistributed here |
| `main_rotate.py` | `YOLO26<size>-MIDI.pt` | YOLO26 oriented-box model, 3 gesture classes | Trained for this project, July 2026 |
| `main_obb.py` | `hbb-s-fold1-320.mlpackage`, else `hbb-s-fold1-320.pt` | YOLO26-s detect model, 3 gesture classes, 320 px | Trained in the research study, August 2026 |

The gesture classes are `thumbout`, `openhand`, `closedhand`.

## MediaPipe

```bash
curl -L -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
```

`src/vision_mediapipe.py` prints this command if the file is missing. This is the only
program that runs with nothing but a public download.

## The hand-pose model for `main.py`

`yolov8n-hand-pose.pt` was not trained in this project. Its metadata records Ultralytics
8.2.15, May 2024, a 224 px training size and the AGPL-3.0 license.

Any Ultralytics pose model with a single hand class and the standard 21-point hand layout can
take its place. `src/logic.py` reads the box of every hand and six keypoints of the left
hand: 0 (wrist), 9 (middle-finger knuckle) and the fingertips 8, 12, 16 and 20. One way to
get such a model is to train a pose model on Ultralytics' hand-keypoints dataset; that was
not tried here. Pass another file with
`UltralyticsVision(model_variant="your-model.pt")` in `main.py`.

## The rotation models for `main_rotate.py`

Five sizes of the same model. `--model n|s|m|l|x` picks `YOLO26<size>-MIDI.pt`; a path to any
other `.pt` also works.

| Size | File size | mAP50-95 | Speed at 640 px on MPS |
|---|---|---|---|
| n (default) | 5.8 MB | 0.49 | ~90 fps |
| s | 21 MB | 0.77 | ~29 fps |
| m | 47 MB | 0.67 | ~25 fps |
| l | 56 MB | 0.80 | ~24 fps |
| x | 126 MB | 0.37 | ~11 fps |

The figures are read from the `YOLO26<size>-ver` files in the project root, one per model.
Each is a small JSON record: base model, dataset, epochs, training size, training date,
Ultralytics version, mAP and measured speed. `src/vision_yolo26.py` derives the file name
from the model name and prints the record at startup; a missing record is skipped, not an
error. Update the record when a model is retrained.

The rotation logic identifies the fist by class index 2, so a replacement model must keep the
class order `thumbout`, `openhand`, `closedhand`.

## The current model for `main_obb.py`

`hbb-s-fold1-320` is fold 1 of the cross-validation in
[midi-gesture-research](https://github.com/hg5210187-ai/midi-gesture-research): YOLO26-s,
axis-aligned boxes, trained at 320 px for 100 epochs. That repository holds everything about
how it was made and why it was chosen:

- `DATA_COLLECTION.md` — how to photograph an equivalent dataset. The images themselves are
  not distributed, because they show an identifiable person.
- `kaggle/train_yolo.py` and `TRAINING_CONFIG.md` — the training driver and the
  hyperparameters as they actually ran.
- `REPORT.md` — accuracy, latency and the deployment choice.

A model you train yourself works here if it is an Ultralytics **detect** model with a class
named `closedhand`. `src/logic_obb.py` uses the right-hand box whatever its class, and reads
the left-hand fist from that class name.

```bash
HBB_MODEL=my-model.pt HBB_IMGSZ=320 uv run python main_obb.py
```

### Exporting to Core ML

The `.pt` runs in PyTorch at 16–22 ms per frame on the M4. The Core ML export of the same
model runs at about 2.3 ms.

```bash
uv run yolo export model=hbb-s-fold1-320.pt format=coreml imgsz=320
```

This writes `hbb-s-fold1-320.mlpackage` (18 MB) next to the `.pt`, and `main_obb.py` picks it
up on the next start. Two things to know:

- `numpy` is pinned to `<=2.3.5` in `pyproject.toml`. NumPy 2.4.1 broke this export.
- The export is close to the original, not identical. Compared on 300 images at confidence
  ≥ 0.6, the two agreed on box count and classes for 278, and Core ML tended to find fewer
  boxes. `OBB_DEBUG=1` prints every detection if hands start dropping out.

`HBB_DEVICE=mps|cpu` applies to PyTorch models only.

## The retired right-hand model

`right_hand_obb.pt` is the first self-trained model: YOLO11n-OBB, one class, trained on 209
right-hand images in June 2026. Only the two-model backend in `src/vision_obb.py` loads it,
and no program uses that backend now. It is described in
[BUILD_FROM_SCRATCH.md](BUILD_FROM_SCRATCH.md#stage-7--the-first-self-trained-detector).
