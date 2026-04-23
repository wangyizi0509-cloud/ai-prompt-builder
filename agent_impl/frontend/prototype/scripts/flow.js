import { setState } from "./mock-store.js";

export const PAGE_IDS = {
  P01: "P01",
  P02: "P02",
  P03: "P03",
  P04: "P04",
  P05: "P05",
  P06: "P06",
  P07: "P07",
};

export const PAGE_FILES = {
  [PAGE_IDS.P01]: "01-home-image.html",
  [PAGE_IDS.P02]: "02-home-text-input.html",
  [PAGE_IDS.P03]: "03-home-upload-trigger.html",
  [PAGE_IDS.P04]: "04-consult-step1.html",
  [PAGE_IDS.P05]: "05-consult-step2-empty.html",
  [PAGE_IDS.P06]: "06-consult-step2-filled.html",
  [PAGE_IDS.P07]: "07-plan-update-cards.html",
};

const FILE_TO_PAGE = Object.entries(PAGE_FILES).reduce((acc, [pageId, file]) => {
  acc[file] = pageId;
  return acc;
}, {});

function inPagesDir() {
  return window.location.pathname.includes("/prototype/pages/");
}

function rootPrefix() {
  return inPagesDir() ? "../" : "";
}

export function resolvePagePath(pageId) {
  const file = PAGE_FILES[pageId] || PAGE_FILES[PAGE_IDS.P01];
  return `${rootPrefix()}pages/${file}`;
}

export function goToPage(pageId, patch = {}) {
  setState({ currentPage: pageId, ...patch });
  const next = resolvePagePath(pageId);
  window.location.href = next;
}

export function goHome() {
  goToPage(PAGE_IDS.P01);
}

export function getPageIdFromPath() {
  const parts = window.location.pathname.split("/");
  const currentFile = parts[parts.length - 1] || "";
  return FILE_TO_PAGE[currentFile] || null;
}

export function syncPageIdFromPath() {
  const pageId = getPageIdFromPath();
  if (pageId) {
    setState({ currentPage: pageId });
  }
  return pageId;
}
