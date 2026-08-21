# VID-001 Elgato recording configuration

This configuration is tailored to the software detected on this Mac:

- Elgato Camera Hub
- Elgato Stream Deck with a 15-key, 5 × 3 layout
- OBS Studio
- Elgato's OBS Studio Stream Deck plugin
- Elgato Prompter managed through `prompter-kit`

## Installed recording flow

Run `./setup-recording.sh` from this directory to create a timestamped backup,
configure Camera Hub and OBS, and install a dedicated `VID-001` folder on the
existing Stream Deck profile. The installer refuses to overwrite the target key
if it contains an unrelated action.

The focused recording surface is `record.html`. It replaces the previous path
through the content dashboard, browser teleprompter, and production manifest.
Camera Hub is the production teleprompter; the browser teleprompter remains only
as a rehearsal fallback.

The installed Stream Deck layout is:

| | Column 1 | Column 2 | Column 3 | Column 4 | Column 5 |
| --- | --- | --- | --- | --- | --- |
| Row 1 | BACK | PREPARE | SLIDES | CHECKLIST | PRIVACY |
| Row 2 | CAMERA | SCREEN | CAMERA + SCREEN | PREVIOUS CHAPTER | NEXT CHAPTER |
| Row 3 | START | PAUSE TEXT | MICROPHONE | RECORDINGS | STOP |

### Row 1 — preparation and safety

- **PREPARE** opens Camera Hub, OBS, and `record.html`.
- **SLIDES** opens the approved presentation.
- **CHECKLIST** opens the printable production resource.
- **PRIVACY** switches OBS to `Intro / BRB`, which must not contain desktop
  capture or tenant data.

### Row 2 — OBS scenes

The controls use explicit global shortcuts against the existing OBS scenes:

- `Cámara`
- `Pantalla`
- `Pantalla + Cámara`
- `Intro / BRB`

`Intro / BRB` must contain no live desktop capture, notifications, tenant
details, or browser content. It is the emergency scene to press before opening
an unexpected window.

### Row 3 — recording safety

- **START** selects the Camera scene, starts OBS recording, waits 700 ms, then
  starts Camera Hub autoscroll. Both visible states must change before speaking.
- **PAUSE TEXT** pauses or resumes the Prompter while OBS continues recording.
  After a mistake, raise a hand, say “marca,” and repeat the complete sentence.
- **MICROPHONE** toggles the existing OBS `Mic/Aux` source.
- **RECORDINGS** opens `~/Movies`.
- **STOP** pauses the Prompter, waits 300 ms, and stops OBS.

Keep START and STOP on opposite corners. Do not use one toggle for both; a
misread button state can stop a good take.

If the Prompter was manually paused, resume it before pressing STOP. This keeps
the toggle state aligned and prevents STOP from restarting the text.

## Camera Hub starting point

These are repeatable starting values, not camera-model-specific absolutes:

- Match Camera Hub and OBS at 30 fps unless the complete production is
  deliberately configured for 25 fps.
- In Spain, use 50 Hz anti-flicker control for mains-powered lighting.
- Lock white balance after lighting is final; do not leave it drifting during a
  take.
- Use manual exposure when available. Start near a 180-degree shutter
  relationship (`1/60` at 30 fps or `1/50` at 25 fps), then control brightness
  with light output and gain.
- Keep gain/ISO as low as the lighting permits.
- Focus once at the seated position, verify the eyes, then lock focus if the
  framing is fixed.
- Save a Camera Hub preset named `JP · YouTube Desk`.
- Put the Prompter at eye level. Use a font size that allows natural eye
  movement, not the maximum amount of text on screen.
- Enable mirroring only when the physical Prompter path requires it. The
  imported script itself remains normal text.

Before every take, verify exposure, focus, white balance, frame rate, and the
selected preset. Automatic settings may be useful during setup but should not
change visibly while recording.

## OBS recording baseline installed

- Canvas and output: `2560 × 1440`.
- Frame rate: match Camera Hub, normally `30 fps`.
- Recording container: `MKV` for crash safety; enable automatic remux to MP4.
- Encoder: Apple hardware H.264 for the compatibility master, using a
  high-quality recording preset rather than a streaming bitrate.
- Audio sample rate: `48 kHz`.
- Track 1: complete monitoring mix.
- Track 2: isolated microphone.
- Track 3: isolated system/demo audio.
- Disable desktop notifications and use a clean macOS desktop profile.
- Record a sync clap and at least ten seconds of room tone.

The installer sets 2560 × 1440, 30 fps, 48 kHz, MKV, Apple H.264, recording
hotkeys, scene hotkeys, and the `Mic/Aux` mute hotkey. It intentionally leaves
the existing audio routing in place; isolated tracks require selecting and
testing the actual microphone and system-audio devices.

After remuxing, rename the deliverables exactly as declared in the episode
manifest. Confirm every expected file has finished syncing before starting the
OpenMontage editing session.

## Elgato Prompter

Use the already imported Camera Hub script named
`VID-001 — Copilot Studio en producción`. Each paragraph in
`camera-script.txt` is a natural rehearsal and pause boundary. Internal slide
and screen cues are intentionally absent from spoken text; those cues remain in
the approved production package for the editor.

Recommended operating method:

1. Press **PREPARE** and complete the preflight in `record.html`.
2. Confirm that Camera Hub shows the exact VID-001 script and is stopped at the
   beginning.
3. Press **START** and verify both OBS recording and text movement before
   speaking.
4. Keep scrolling slightly slower than natural speech.
5. Pause at the end of a chapter instead of racing the scroll.
6. After a mistake, pause the text, raise a hand, say “marca,” and repeat the
   complete sentence.
7. For live demos, keep the Prompter visible only for the current explanation;
   do not read while searching through the interface.

Camera Hub global shortcuts require macOS Accessibility permission for Camera
Hub and Stream Deck. If START records but does not move the text, enable both in
**System Settings → Privacy & Security → Accessibility**, then restart both
applications.
