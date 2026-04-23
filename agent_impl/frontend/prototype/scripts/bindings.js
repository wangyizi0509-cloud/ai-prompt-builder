import { getState, setState, resetState, subscribe } from "./mock-store.js";
import { goToPage, PAGE_IDS, syncPageIdFromPath } from "./flow.js";

function safeEl(selector) {
  return document.querySelector(selector);
}

export function initCommonPage(pageId) {
  syncPageIdFromPath();
  setState({ currentPage: pageId });
  wireQuickNav();
}

export function wireQuickNav() {
  document.querySelectorAll("[data-go-page]").forEach((node) => {
    node.addEventListener("click", () => {
      const target = node.getAttribute("data-go-page");
      if (target) goToPage(target);
    });
  });
}

export function wireCloseToHome(selector = "[data-close-home]") {
  document.querySelectorAll(selector).forEach((node) => {
    node.addEventListener("click", () => goToPage(PAGE_IDS.P01));
  });
}

export function wireResetButton(selector = "#reset-demo") {
  const node = safeEl(selector);
  if (!node) return;
  node.addEventListener("click", () => {
    resetState();
    window.alert("Mock 状态已重置");
  });
}

export function wireContinueButton(selector = "#continue-demo") {
  const node = safeEl(selector);
  if (!node) return;
  node.addEventListener("click", () => {
    const state = getState();
    goToPage(state.currentPage || PAGE_IDS.P01);
  });
}

export function wireDraftInput(selector) {
  const input = safeEl(selector);
  if (!input) return;
  const state = getState();
  if (state.draftText) {
    input.value = state.draftText;
  }
  input.addEventListener("input", () => {
    setState({ draftText: input.value });
  });
}

export function wireExtraInput(selector) {
  const input = safeEl(selector);
  if (!input) return;
  const state = getState();
  if (state.extraInfo) {
    input.value = state.extraInfo;
  }
  input.addEventListener("input", () => {
    setState({ extraInfo: input.value });
  });
}

export function mountStateText(selector, pick) {
  const node = safeEl(selector);
  if (!node) return () => {};
  return subscribe((state) => {
    const next = pick(state);
    node.textContent = next == null || next === "" ? "-" : String(next);
  });
}

export function buildThumbList(containerSelector, { includeMore = true } = {}) {
  const container = safeEl(containerSelector);
  if (!container) return;
  const state = getState();
  const images = state.uploadedImages;
  const fallback = ["城堡", "菜单", "会话", "冰淇淋"];
  const list = images.length > 0 ? images : fallback;
  const visible = list.slice(0, 4);

  container.innerHTML = "";
  visible.forEach((item, idx) => {
    const thumb = document.createElement("div");
    thumb.className = `thumb-item${idx >= 3 ? " dark" : ""}`;
    thumb.textContent = item.slice(0, 2);
    container.appendChild(thumb);
  });

  if (includeMore) {
    const more = document.createElement("div");
    more.className = "thumb-item thumb-more";
    const extra = list.length > 4 ? list.length - 4 : 10;
    more.textContent = `+${extra}`;
    container.appendChild(more);
  }
}

export function wireUploadInput({ inputSelector, previewSelector, countSelector }) {
  const fileInput = safeEl(inputSelector);
  const preview = safeEl(previewSelector);
  const countNode = countSelector ? safeEl(countSelector) : null;
  if (!fileInput) return;

  const refresh = () => {
    const state = getState();
    if (preview) {
      preview.innerHTML = "";
      const items = state.uploadedImages.slice(0, 4);
      if (items.length === 0) {
        const placeholder = document.createElement("div");
        placeholder.className = "text-muted";
        placeholder.style.fontSize = "13px";
        placeholder.textContent = "还未选择图片";
        preview.appendChild(placeholder);
      } else {
        items.forEach((name, idx) => {
          const node = document.createElement("div");
          node.className = `thumb-item${idx >= 3 ? " dark" : ""}`;
          node.textContent = name.slice(0, 2);
          preview.appendChild(node);
        });
      }
    }
    if (countNode) {
      countNode.textContent = String(state.uploadCount || 0);
    }
  };

  fileInput.addEventListener("change", () => {
    const files = Array.from(fileInput.files || []);
    if (files.length === 0) return;
    const names = files.slice(0, 12).map((f, idx) => {
      const base = (f.name || `截图${idx + 1}`).replace(/\.[^/.]+$/, "");
      return base.slice(0, 6);
    });
    const state = getState();
    const next = [...state.uploadedImages, ...names].slice(0, 20);
    setState({ uploadedImages: next, uploadCount: next.length, uploadIntent: true });
    refresh();
  });

  refresh();
}

export function wireChoiceButtons(selector, stateKey) {
  const nodes = document.querySelectorAll(selector);
  const state = getState();
  nodes.forEach((node) => {
    const value = node.getAttribute("data-value") || "";
    if (state[stateKey] === value) {
      node.classList.add("active");
    }
    node.addEventListener("click", () => {
      setState({ [stateKey]: value });
      nodes.forEach((other) => other.classList.remove("active"));
      node.classList.add("active");
    });
  });
}

export function wireInputMirror(inputSelector, stateKey) {
  const input = safeEl(inputSelector);
  if (!input) return;
  const state = getState();
  if (state[stateKey]) {
    input.value = state[stateKey];
  }
  input.addEventListener("input", () => {
    setState({ [stateKey]: input.value });
  });
}

export function updateLoadingTag(selector, loading) {
  const node = safeEl(selector);
  if (!node) return;
  node.classList.toggle("hidden", !loading);
}
