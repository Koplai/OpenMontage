# VID-001 Elgato recording configuration

This configuration is tailored to the software detected on this Mac:

- Elgato Camera Hub
- Elgato Stream Deck with a 15-key, 5 × 3 layout
- OBS Studio
- Elgato's OBS Studio Stream Deck plugin
- Elgato Prompter managed through `prompter-kit`

## Stream Deck profile: JPMarquez Studio

Create a dedicated profile instead of modifying the default profile. Use this
layout:

| | Column 1 | Column 2 | Column 3 | Column 4 | Column 5 |
| --- | --- | --- | --- | --- | --- |
| Row 1 | PREP | CAMERA HUB | SLIDES | INBOX | EDIT |
| Row 2 | CAMERA | DEMO | CAMERA + DEMO | FULL SLIDE | PRIVACY |
| Row 3 | START | PAUSE | MUTE | MARK | STOP |

### Row 1 — production system

- **PREP**: Multi Action → open Camera Hub, open OBS, and switch to the
  `JP · Camera` scene.
- **CAMERA HUB**: System → Open → `/Applications/Elgato Camera Hub.app`
- **SLIDES**: System → Open the approved `video-001/slides.html` file.
- **INBOX**: System → Open the permanent VID-001 OneDrive recording folder.
- **EDIT**: leave unassigned for VID-001. Start the OpenMontage editing session
  only after manually confirming the complete recording set.

### Row 2 — OBS scenes

Use the installed OBS Studio plugin and create these exact scene names:

- `JP · Camera`
- `JP · Demo`
- `JP · Camera + Demo`
- `JP · Full Slide`
- `JP · Privacy`

`JP · Privacy` must contain no live desktop capture, notifications, tenant
details, or browser content. It is the emergency scene to press before opening
an unexpected window.

### Row 3 — recording safety

- **START**: Multi Action:
  1. OBS → switch to `JP · Camera`.
  2. OBS → Start Recording.
- **PAUSE**: OBS → Pause Recording.
- **MUTE**: OBS → Mute source for the dedicated microphone.
- **MARK**: use a visible hand raise and say “marca” after a mistake, then pause
  and repeat the complete sentence. This gives the editor both waveform and
  visual evidence without relying on an unverified plugin.
- **STOP**: OBS → Stop Recording.

Keep START and STOP on opposite corners. Do not use one toggle for both; a
misread button state can stop a good take.

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

## OBS recording baseline

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

1. Read one chapter ahead before recording.
2. Keep scrolling slightly slower than natural speech.
3. Pause at the end of a chapter instead of racing the scroll.
4. Press **MARK** after a mistake and repeat the complete sentence.
5. For live demos, keep the Prompter visible only for the current explanation;
   do not read while searching through the interface.
