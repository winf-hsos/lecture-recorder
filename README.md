# Lecture Recorder

A small Windows app for recording lectures locally with OBS Studio, built as a replacement for recording through Microsoft Teams. It records screen, webcam and microphone in one go and afterwards files two synchronized MP4 videos (screen and camera) into a folder per term and module.

OBS does the capturing and encoding in the background, while the app gives you a compact window to pick module and devices and turns into a slim bar while you are recording. The user interface is in German, because it was written for teaching at a German university; code, comments and this documentation are in English.

| Before recording | After stopping |
|---|---|
| ![Setup view](docs/screenshots/setup.png) | ![Result](docs/screenshots/result.png) |

While recording, the window shrinks to a slim bar that turns yellow when paused and can be minimized (the hotkeys keep working), and stopping asks whether to keep the recording:

![Recording bar](docs/screenshots/recording.png)

![Paused bar](docs/screenshots/paused.png)

![Save question](docs/screenshots/save-question.png)

## Features

- **Screen, camera and microphone are selectable**, and the microphone level is shown live, so you notice a muted mic before the lecture starts.
- **The window itself is never recorded.** It stays visible on your screen but is excluded from capture (`SetWindowDisplayAffinity`).
- **The taskbar is left out** of the screen track by default, using the work area of the selected monitor.
- **The Alt+Tab overview is hidden.** The Windows task switcher cannot be excluded from capture, so the app logs when you press Alt+Tab and freezes the screen track for that moment afterwards, while audio and camera keep running.
- **Pause and resume** with a button or a global hotkey.
- **Save, continue or discard**: stopping first pauses the recording and asks what to do, so an accidental stop costs nothing. A discarded recording goes to the recycle bin.
- **Two MP4 files per session**, for example `2026-10-09 - Regression - Bildschirm.mp4` and `… - Kamera.mp4`, filed under `<archive>\<term>\<module>\`. Both tracks share the same audio and start at the same instant, so they can be placed side by side in an editor without syncing.
- **Configurable folders** for the archive and for the raw recordings, plus an "open in folder" button once a recording is filed.
- **Moderate load and file size**: hardware encoding on NVIDIA (NVENC) with constant quality, about 3.4 GB per hour for the raw recording.

## Requirements

- Windows 10 or 11
- [OBS Studio](https://obsproject.com/) 28 or later, which ships with obs-websocket
- An NVIDIA GPU with NVENC (used both by OBS and for splitting)
- [ffmpeg](https://ffmpeg.org/) with `h264_nvenc`, on the `PATH`
- Python 3.10 or later with the packages from `requirements.txt`

```bash
pip install -r requirements.txt
```

## Setup

1. In OBS, open **Tools → WebSocket Server Settings**, enable the server on port 4455 and set a password.
2. Store that password in the user environment variable `OBS_WEBSOCKET_PASSWORD`. The app reads it from there and never prints it.
3. Optionally run `python tools/setup_obs.py` once to check the connection and list the devices OBS sees.

On first start the app creates its own OBS profile and scene collection named `Lecture`, with a wide 3840×1200 canvas that holds the screen on the left and the webcam on the right. Existing OBS profiles are not touched.

## Usage

Start the app with `lecture-recorder.cmd` (no console window) or `python recorder.py`. OBS is started minimized to the tray if it is not running yet.

1. Pick or type the module and optionally a topic for the session; both go into the file name.
2. Check screen, camera and microphone, and watch the level bar.
3. Click **Aufnahme starten** or press **Ctrl+Alt+R**. The window shrinks to a bar at the top of the screen.
4. Pause and resume with the pause button or **Ctrl+Alt+P**.
5. Stop with the stop button, or press **Ctrl+Alt+R** twice within three seconds (the double press protects against stopping a lecture with a stray keystroke). The recording is paused and the bar asks whether to save it: **Speichern** files it, **Weiter** continues recording, and **Verwerfen** (click twice) moves the raw file to the recycle bin.

After stopping, the recording is split and encoded into the two MP4 files, and the raw MKV is deleted only once both outputs have been checked to be as long as the source. If splitting fails, the raw file is kept.

The current term is derived from the date: winter term from 1 September to the end of February, summer term from 1 March. Folder names follow the pattern `2026-27 - WS` and `2026 - SS`. Module suggestions come from the folders that already exist for the term, and optionally from a Markdown file whose `## ` headings are module names (`module_file` in the settings).

Settings are stored in `%APPDATA%\lecture-recorder\settings.json`.

## How it works

| File | Role |
|---|---|
| `recorder.py` | Window and JavaScript bridge (pywebview with Edge WebView2), single instance, capture exclusion |
| `ui.html` | The user interface |
| `core.py` | Settings, device selection, recording state, hotkey handling, split after stopping |
| `obs_remote.py` | Minimal obs-websocket v5 client and OBS startup |
| `obs_scene.py` | OBS profile, scene, sources, encoder settings, screen crop |
| `monitors.py` | Monitor geometry and taskbar margins from Windows |
| `hotkeys.py` | Global hotkeys and a low-level keyboard hook that detects Alt+Tab |
| `split.py` | ffmpeg split into screen and camera track, freezing the Alt+Tab spans; also usable on the command line |
| `tools/benchmark.py` | Test recording that measures CPU, GPU and encoder load |

Hiding Alt+Tab needs a small correction: the time OBS reports runs about 0.55 seconds ahead of the picture that ends up in the file, so the detected spans are shifted by that delay and padded a little on both sides before they are frozen.

## Limitations

- Windows only, and splitting assumes an NVIDIA GPU.
- The camera field is 1920×1080; the screen field holds up to 1920×1200.
- Streaming (for example to YouTube) is not built in yet.
