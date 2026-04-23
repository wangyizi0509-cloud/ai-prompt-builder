const STORAGE_KEY = "crush_demo_mock_v1";

const defaultState = {
  currentPage: "P01",
  draftText: "",
  uploadedImages: [],
  uploadCount: 0,
  uploadIntent: false,
  tone: "",
  speed: "",
  speedExtra: "",
  extraInfo: "",
};

let cachedState = loadFromStorage();
const listeners = new Set();

function loadFromStorage() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...defaultState };
    const parsed = JSON.parse(raw);
    return normalizeState(parsed);
  } catch (_) {
    return { ...defaultState };
  }
}

function normalizeState(input) {
  const source = input && typeof input === "object" ? input : {};
  const uploadedImages = Array.isArray(source.uploadedImages)
    ? source.uploadedImages.filter((item) => typeof item === "string").slice(0, 20)
    : [];

  return {
    ...defaultState,
    ...source,
    uploadedImages,
    uploadCount: Number.isFinite(source.uploadCount) ? Math.max(0, source.uploadCount) : uploadedImages.length,
  };
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cachedState));
  } catch (_) {
    // no-op: private browsing may disable localStorage
  }
}

function emit() {
  const snapshot = getState();
  listeners.forEach((listener) => {
    try {
      listener(snapshot);
    } catch (_) {
      // no-op
    }
  });
}

export function getState() {
  return JSON.parse(JSON.stringify(cachedState));
}

export function setState(patch) {
  const nextPatch = typeof patch === "function" ? patch(getState()) : patch;
  if (!nextPatch || typeof nextPatch !== "object") {
    return getState();
  }
  cachedState = normalizeState({ ...cachedState, ...nextPatch });
  persist();
  emit();
  return getState();
}

export function resetState() {
  cachedState = { ...defaultState };
  persist();
  emit();
  return getState();
}

export function subscribe(listener) {
  if (typeof listener !== "function") {
    return () => {};
  }
  listeners.add(listener);
  listener(getState());
  return () => listeners.delete(listener);
}

window.addEventListener("storage", (event) => {
  if (event.key !== STORAGE_KEY) return;
  cachedState = loadFromStorage();
  emit();
});

export { STORAGE_KEY, defaultState };
