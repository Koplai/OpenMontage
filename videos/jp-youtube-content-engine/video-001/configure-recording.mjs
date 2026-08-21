#!/usr/bin/env node

import { randomUUID } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { basename, join, resolve } from "node:path";

const SCRIPT_ID = "C12B7AD5-19D5-4814-A758-72E1755C94DC";
const LEGACY_PROFILE_KEY = "a4c11a7e-1d01-4d85-9b7a-0f4a67d00101";
const ORIGINAL_PROFILE_ID = "B7E80119-9C3B-4CC7-90B2-1B55E7A00101";
const ORIGINAL_PROFILE_KEY = ORIGINAL_PROFILE_ID.toLowerCase();

function readArgs() {
  const args = {};
  for (let index = 2; index < process.argv.length; index += 2) {
    const key = process.argv[index]?.replace(/^--/, "");
    const value = process.argv[index + 1];
    if (!key || !value) {
      throw new Error(`Invalid argument near ${process.argv[index] ?? "end of command"}`);
    }
    args[key] = resolve(value);
  }

  const required = [
    "camera-settings",
    "obs-profile",
    "obs-scenes",
    "streamdeck-profile",
    "repo-root",
  ];
  for (const key of required) {
    if (!args[key]) throw new Error(`Missing --${key}`);
    if (!existsSync(args[key])) throw new Error(`Path does not exist: ${args[key]}`);
  }
  return args;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 4)}\n`);
}

function setPrompterProperty(device, key, value) {
  const property = device.properties?.find(
    (candidate) => candidate.jsonKeyPrompterPropertyId === key,
  );
  if (!property) throw new Error(`Camera Hub property not found: ${key}`);
  property.PropertyCurrentValue.PropertyValue = value;
}

function configureCameraHub(path) {
  const settings = readJson(path);
  const devices = settings["applogic.prompter.devices"];
  const selectedId = settings["applogic.prompter.lastSelectedPrompterV3"];
  const device = devices?.find((candidate) => candidate.deviceId === selectedId);

  if (!device) throw new Error("The selected Elgato Prompter was not found in Camera Hub");

  settings["applogic.prompter.hotkeys.enable"] = true;
  device.source = {
    ...(device.source ?? {}),
    channelId: "",
    textId: SCRIPT_ID,
    type: 1,
  };
  setPrompterProperty(device, "PrompterMode", 1);
  setPrompterProperty(device, "Autoscroll", false);
  setPrompterProperty(device, "AutoLoop", false);
  setPrompterProperty(device, "EnableReadTextHighlightingNew", true);

  writeJson(path, settings);
}

function setIniValue(input, section, key, value) {
  const lines = input.split(/\r?\n/);
  const sectionHeader = `[${section}]`;
  let sectionIndex = lines.indexOf(sectionHeader);

  if (sectionIndex === -1) {
    if (lines.at(-1) !== "") lines.push("");
    lines.push(sectionHeader, `${key}=${value}`);
    return lines.join("\n");
  }

  let sectionEnd = lines.length;
  for (let index = sectionIndex + 1; index < lines.length; index += 1) {
    if (/^\[.+\]$/.test(lines[index])) {
      sectionEnd = index;
      break;
    }
  }

  const keyPrefix = `${key}=`;
  const keyIndex = lines.findIndex(
    (line, index) =>
      index > sectionIndex && index < sectionEnd && line.startsWith(keyPrefix),
  );
  if (keyIndex === -1) {
    lines.splice(sectionEnd, 0, `${key}=${value}`);
  } else {
    lines[keyIndex] = `${key}=${value}`;
  }
  return lines.join("\n");
}

function obsBinding(key) {
  return JSON.stringify([{ key, control: true, command: true }]);
}

function configureObsProfile(path) {
  let profile = readFileSync(path, "utf8");
  const values = [
    ["Video", "BaseCX", "2560"],
    ["Video", "BaseCY", "1440"],
    ["Video", "OutputCX", "2560"],
    ["Video", "OutputCY", "1440"],
    ["Video", "FPSType", "0"],
    ["Video", "FPSCommon", "30"],
    ["Audio", "SampleRate", "48000"],
    ["SimpleOutput", "RecFormat2", "mkv"],
    ["SimpleOutput", "RecEncoder", "apple_h264"],
    ["Hotkeys", "OBSBasic.StartRecording", obsBinding("OBS_KEY_R")],
    ["Hotkeys", "OBSBasic.StopRecording", obsBinding("OBS_KEY_S")],
    ["Hotkeys", "OBSBasic.PauseRecording", obsBinding("OBS_KEY_SPACE")],
    ["Hotkeys", "OBSBasic.UnpauseRecording", obsBinding("OBS_KEY_SPACE")],
  ];
  for (const [section, key, value] of values) {
    profile = setIniValue(profile, section, key, value);
  }
  writeFileSync(path, profile.endsWith("\n") ? profile : `${profile}\n`);
}

function configureObsScenes(path) {
  const scenes = readJson(path);
  const bindings = new Map([
    ["Cámara", "OBS_KEY_1"],
    ["Pantalla", "OBS_KEY_2"],
    ["Pantalla + Cámara", "OBS_KEY_3"],
    ["Intro / BRB", "OBS_KEY_4"],
  ]);

  for (const source of scenes.sources ?? []) {
    const key = bindings.get(source.name);
    if (!key) continue;
    source.hotkeys ??= {};
    source.hotkeys["OBSBasic.SelectScene"] = JSON.parse(obsBinding(key));
  }

  if (!scenes.AuxAudioDevice1) throw new Error("OBS Mic/Aux source was not found");
  scenes.AuxAudioDevice1.hotkeys ??= {};
  const micBinding = JSON.parse(obsBinding("OBS_KEY_M"));
  scenes.AuxAudioDevice1.hotkeys["libobs.mute"] = micBinding;
  scenes.AuxAudioDevice1.hotkeys["libobs.unmute"] = micBinding;
  writeJson(path, scenes);
}

const emptyKey = {
  KeyCmd: false,
  KeyCtrl: false,
  KeyModifiers: 0,
  KeyOption: false,
  KeyShift: false,
  NativeCode: -1,
  QTKeyCode: 33554431,
  VKeyCode: -1,
};

const keyCodes = {
  "1": [18, 49],
  "2": [19, 50],
  "3": [20, 51],
  "4": [21, 52],
  M: [46, 77],
  P: [35, 80],
  R: [15, 82],
  S: [1, 83],
  SPACE: [49, 32],
  PAGE_UP: [116, 16777238],
  PAGE_DOWN: [121, 16777239],
  LEFT: [123, 16777234],
  RIGHT: [124, 16777236],
};

function hotkeySettings(key, { command = true, control = true } = {}) {
  const codes = keyCodes[key];
  if (!codes) throw new Error(`Unknown Stream Deck key: ${key}`);
  const [nativeCode, qtKeyCode] = codes;
  return {
    Coalesce: true,
    Hotkeys: [
      {
        KeyCmd: command,
        KeyCtrl: control,
        KeyModifiers: command && control ? 10 : 0,
        KeyOption: false,
        KeyShift: false,
        NativeCode: nativeCode,
        QTKeyCode: qtKeyCode,
        VKeyCode: nativeCode,
      },
      { ...emptyKey },
      { ...emptyKey },
      { ...emptyKey },
    ],
  };
}

function actionState(image) {
  return [
    {
      Image: image,
      ShowTitle: false,
      Title: "",
      TitleAlignment: "bottom",
      TitleColor: "#ffffff",
    },
  ];
}

function baseAction(name, uuid, image, settings = {}) {
  return {
    ActionID: randomUUID(),
    LinkedTitle: true,
    Name: name,
    Resources: null,
    Settings: settings,
    State: 0,
    States: actionState(image),
    UUID: uuid,
  };
}

function hotkeyAction(name, key, image, modifiers) {
  return baseAction(
    name,
    "com.elgato.streamdeck.system.hotkey",
    image,
    hotkeySettings(key, modifiers),
  );
}

function openAction(name, path, image) {
  return baseAction(name, "com.elgato.streamdeck.system.open", image, {
    path: JSON.stringify(path),
  });
}

function delayAction(milliseconds) {
  return {
    ActionID: randomUUID(),
    LinkedTitle: false,
    Name: "Delay",
    Resources: null,
    Settings: { delay: milliseconds, duration: milliseconds },
    State: 0,
    States: [{ Image: "", Title: "" }],
    UUID: "com.elgato.streamdeck.multiactions.delay",
  };
}

function multiAction(name, actions, image) {
  return {
    ...baseAction(name, "com.elgato.streamdeck.multiactions.routine", image),
    Actions: [{ Actions: actions }],
  };
}

function escapeXml(value) {
  return value.replace(/[<>&'"]/g, (character) => {
    const entities = { "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" };
    return entities[character];
  });
}

function writeIcon(imagesPath, id, lines, color, symbol = "") {
  const fileName = `${id}.svg`;
  const safeLines = lines.map(escapeXml);
  const lineMarkup = safeLines
    .map(
      (line, index) =>
        `<text x="72" y="${98 + index * 22}" text-anchor="middle" fill="#F7FAFF" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="${safeLines.length === 1 ? 18 : 15}" font-weight="800">${line}</text>`,
    )
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 144 144">
  <rect width="144" height="144" rx="24" fill="#0A1628"/>
  <rect x="5" y="5" width="134" height="134" rx="20" fill="${color}" fill-opacity=".22" stroke="${color}" stroke-width="3"/>
  <text x="72" y="66" text-anchor="middle" fill="${color}" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="34" font-weight="900">${escapeXml(symbol)}</text>
  ${lineMarkup}
</svg>`;
  writeFileSync(join(imagesPath, fileName), svg);
  return `Images/${fileName}`;
}

function findMainPage(profilePath) {
  const manifest = readJson(join(profilePath, "manifest.json"));
  const pageId = manifest.Pages?.Current ?? manifest.Pages?.Default;
  if (pageId && existsSync(join(profilePath, "Profiles", pageId, "manifest.json"))) {
    return pageId;
  }

  const pagesPath = join(profilePath, "Profiles");
  const candidates = readdirSync(pagesPath).filter((entry) =>
    existsSync(join(pagesPath, entry, "manifest.json")),
  );
  if (candidates.length === 0) throw new Error("No Stream Deck pages were found");
  return candidates[0];
}

function configureStreamDeck(profilePath, repoRoot) {
  const pageId = findMainPage(profilePath);
  const rootPagePath = join(profilePath, "Profiles", pageId);
  const rootManifestPath = join(rootPagePath, "manifest.json");
  const rootManifest = readJson(rootManifestPath);
  const rootActions = rootManifest.Controllers?.[0]?.Actions;
  if (!rootActions) throw new Error("The Stream Deck main page has no action collection");

  const imagesPath = join(rootPagePath, "Images");
  mkdirSync(imagesPath, { recursive: true });

  const icons = {
    original: writeIcon(imagesPath, "original", ["ORIGINAL"], "#9FC9F7", "JP"),
    prep: writeIcon(imagesPath, "prep", ["PREPARAR"], "#C4A35A", "1"),
    slides: writeIcon(imagesPath, "slides", ["SLIDES"], "#4A90E2", "▣"),
    privacy: writeIcon(imagesPath, "privacy", ["PRIVACIDAD"], "#F07474", "■"),
    camera: writeIcon(imagesPath, "camera", ["CÁMARA"], "#59C99A", "●"),
    screen: writeIcon(imagesPath, "screen", ["PANTALLA"], "#4A90E2", "▭"),
    pip: writeIcon(imagesPath, "pip", ["CÁMARA", "+ PANT."], "#9FC9F7", "◫"),
    slidePrevious: writeIcon(imagesPath, "slide-previous", ["SLIDE", "ANTERIOR"], "#4A90E2", "‹"),
    slideNext: writeIcon(imagesPath, "slide-next", ["SLIDE", "SIGUIENTE"], "#4A90E2", "›"),
    chapterPrevious: writeIcon(imagesPath, "chapter-previous", ["CAPÍTULO", "ANTERIOR"], "#C4A35A", "‹"),
    chapterNext: writeIcon(imagesPath, "chapter-next", ["CAPÍTULO", "SIGUIENTE"], "#C4A35A", "›"),
    start: writeIcon(imagesPath, "start", ["EMPEZAR"], "#59C99A", "▶"),
    script: writeIcon(imagesPath, "script", ["PAUSA", "TEXTO"], "#F2BD62", "Ⅱ"),
    mic: writeIcon(imagesPath, "mic", ["MICRÓFONO"], "#9FC9F7", "M"),
    stop: writeIcon(imagesPath, "stop", ["TERMINAR"], "#F07474", "■"),
  };

  const originalPath = join(profilePath, "Profiles", ORIGINAL_PROFILE_ID);
  const originalManifestPath = join(originalPath, "manifest.json");
  if (!existsSync(originalManifestPath)) {
    const originalImagesPath = join(originalPath, "Images");
    mkdirSync(originalImagesPath, { recursive: true });
    cpSync(imagesPath, originalImagesPath, { recursive: true });
    const originalActions = Object.fromEntries(
      Object.entries(rootActions).filter(
        ([, action]) => action.Settings?.ProfileUUID !== LEGACY_PROFILE_KEY,
      ),
    );
    const originalBackIcon = writeIcon(
      originalImagesPath,
      "back",
      ["VOLVER"],
      "#9FC9F7",
      "←",
    );
    originalActions["3,0"] = baseAction(
      "Return to recording controls",
      "com.elgato.streamdeck.profile.backtoparent",
      originalBackIcon,
    );
    writeJson(originalManifestPath, {
      Controllers: [{ Actions: originalActions, Type: "Keypad" }],
      Icon: "",
      Name: "Controles originales",
    });
  }

  const videoPath = join(repoRoot, "videos", "jp-youtube-content-engine", "video-001");
  const cameraHubPath = "/Applications/Elgato Camera Hub.app";
  const obsPath = "/Applications/OBS.app";
  const recordPath = join(videoPath, "record.html");
  const slidesPath = join(videoPath, "slides.html");
  const actions = {
    "0,0": baseAction(
      "Open original controls",
      "com.elgato.streamdeck.profile.openchild",
      icons.original,
      { ProfileUUID: ORIGINAL_PROFILE_KEY },
    ),
    "1,0": multiAction(
      "Prepare VID-001",
      [
        openAction("Open Camera Hub", cameraHubPath, ""),
        delayAction(500),
        openAction("Open OBS", obsPath, ""),
        delayAction(500),
        openAction("Open recording cockpit", recordPath, ""),
      ],
      icons.prep,
    ),
    "2,0": openAction("Open slides", slidesPath, icons.slides),
    "3,0": hotkeyAction("Mute or unmute microphone", "M", icons.mic),
    "4,0": hotkeyAction("Privacy scene", "4", icons.privacy),
    "0,1": hotkeyAction("Camera scene", "1", icons.camera),
    "1,1": hotkeyAction("Screen scene", "2", icons.screen),
    "2,1": hotkeyAction("Camera plus screen scene", "3", icons.pip),
    "3,1": hotkeyAction(
      "Previous slide",
      "LEFT",
      icons.slidePrevious,
      { command: false, control: false },
    ),
    "4,1": hotkeyAction(
      "Next slide",
      "RIGHT",
      icons.slideNext,
      { command: false, control: false },
    ),
    "0,2": multiAction(
      "Start recording and Prompter",
      [
        hotkeyAction("Select camera scene", "1", ""),
        delayAction(250),
        hotkeyAction("Start OBS recording", "R", ""),
        delayAction(700),
        hotkeyAction("Start Prompter", "P", ""),
      ],
      icons.start,
    ),
    "1,2": hotkeyAction("Pause or resume Prompter", "P", icons.script),
    "2,2": hotkeyAction(
      "Previous Prompter chapter",
      "PAGE_UP",
      icons.chapterPrevious,
    ),
    "3,2": hotkeyAction(
      "Next Prompter chapter",
      "PAGE_DOWN",
      icons.chapterNext,
    ),
    "4,2": multiAction(
      "Stop Prompter and recording",
      [
        hotkeyAction("Pause Prompter", "P", ""),
        delayAction(300),
        hotkeyAction("Stop OBS recording", "S", ""),
      ],
      icons.stop,
    ),
  };

  rootManifest.Controllers[0].Actions = actions;
  writeJson(rootManifestPath, rootManifest);
}

function main() {
  const args = readArgs();
  configureCameraHub(args["camera-settings"]);
  configureObsProfile(args["obs-profile"]);
  configureObsScenes(args["obs-scenes"]);
  configureStreamDeck(args["streamdeck-profile"], args["repo-root"]);
  console.log(
    `Configured Camera Hub, OBS, and ${basename(args["streamdeck-profile"])} for VID-001.`,
  );
}

main();
