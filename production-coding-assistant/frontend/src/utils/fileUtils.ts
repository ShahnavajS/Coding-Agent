import type { FileNode } from "../types";
import type { FileInfo } from "./api";

export function getFileIcon(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  const iconMap: Record<string, string> = {
    ts: "TS",
    tsx: "TSX",
    js: "JS",
    jsx: "JSX",
    py: "PY",
    json: "{}",
    css: "CSS",
    html: "HTML",
    md: "MD",
    yml: "YML",
    yaml: "YML",
    env: "ENV",
  };

  return iconMap[ext] || "FILE";
}

export function getLanguageFromFileName(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  const languageMap: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    json: "json",
    css: "css",
    html: "html",
    md: "markdown",
    yml: "yaml",
    yaml: "yaml",
  };

  return languageMap[ext] || "text";
}

export function findFileNodeById(nodes: FileNode[], id: string): FileNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findFileNodeById(node.children, id);
      if (found) return found;
    }
  }
  return null;
}

export function flattenFileTree(nodes: FileNode[]): FileNode[] {
  const result: FileNode[] = [];
  for (const node of nodes) {
    result.push(node);
    if (node.children) {
      result.push(...flattenFileTree(node.children));
    }
  }
  return result;
}

export function buildFileTree(files: FileInfo[]): FileNode[] {
  const root: FileNode[] = [];
  const map = new Map<string, FileNode>();

  const ensureFolder = (folderPath: string): FileNode => {
    const normalized = folderPath.replace(/^\/+/, "");
    const existing = map.get(normalized);
    if (existing) return existing;

    const parts = normalized.split("/").filter(Boolean);
    const name = parts[parts.length - 1] || normalized;
    const node: FileNode = {
      id: normalized || "root",
      name,
      type: "folder",
      path: normalized,
      children: [],
      isOpen: parts.length <= 1,
    };
    map.set(normalized, node);

    if (parts.length === 1) {
      root.push(node);
    } else {
      const parent = ensureFolder(parts.slice(0, -1).join("/"));
      parent.children = parent.children || [];
      if (!parent.children.find((child) => child.id === node.id)) {
        parent.children.push(node);
      }
    }
    return node;
  };

  const sortedFiles = [...files].sort((left, right) => left.path.localeCompare(right.path));
  for (const file of sortedFiles) {
    const normalized = file.path.replace(/^\/+/, "");
    const parts = normalized.split("/").filter(Boolean);
    if (file.type === "folder") {
      ensureFolder(normalized);
      continue;
    }

    const fileNode: FileNode = {
      id: normalized,
      name: file.name,
      type: "file",
      path: normalized,
      size: file.size,
    };

    if (parts.length === 1) {
      root.push(fileNode);
      continue;
    }

    const parent = ensureFolder(parts.slice(0, -1).join("/"));
    parent.children = parent.children || [];
    parent.children.push(fileNode);
  }

  return root;
}

export function formatDate(date: Date): string {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

export const highlightDiff = (
  original: string,
  modified: string
): { lines: string[]; isAdded: boolean[] } => {
  const originalLines = original.split("\n");
  const modifiedLines = modified.split("\n");
  const changes: string[] = [];
  const isAdded: boolean[] = [];

  for (let index = 0; index < Math.max(originalLines.length, modifiedLines.length); index += 1) {
    const originalLine = originalLines[index] || "";
    const modifiedLine = modifiedLines[index] || "";
    changes.push(modifiedLine);
    isAdded.push(originalLine !== modifiedLine);
  }

  return { lines: changes, isAdded };
};
