import { useMemo, useState } from "react";
import {
  ChevronRight, FilePlus2, FolderPlus, RefreshCw,
  Search, Trash2, MoreHorizontal, Folder,
} from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { fileAPI } from "../../utils/api";
import { buildFileTree, getFileIcon, getLanguageFromFileName } from "../../utils/fileUtils";
import type { FileNode } from "../../types";

/* ── File icon colour by extension ──────────────────────────────── */
function fileColour(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    ts: "#3b82f6", tsx: "#3b82f6", js: "#f59e0b", jsx: "#f59e0b",
    py: "#3b9467", json: "#dcdcaa", md: "#9ca3af", css: "#8b5cf6",
    html: "#e36618", sh: "#6ee7b7", toml: "#ce9178", txt: "#9ca3af",
  };
  return map[ext] ?? "#9ca3af";
}

/* ── Single file/folder row ──────────────────────────────────────── */
function FileTreeItem({
  node, depth, onFileSelect, onToggleFolder, onDeletePath, onCreatePath,
}: {
  node: FileNode; depth: number;
  onFileSelect(n: FileNode): void;
  onToggleFolder(n: FileNode): void;
  onDeletePath(n: FileNode): void;
  onCreatePath(type: "file" | "folder", basePath?: string): void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const indent = depth * 12 + 8;
  const isFolder = node.type === "folder";

  return (
    <div style={{ position: "relative" }}>
      {/* Row */}
      <div
        className="file-item"
        style={{ paddingLeft: indent }}
        onClick={() => isFolder ? onToggleFolder(node) : onFileSelect(node)}
      >
        {/* Indent guide lines */}
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} style={{
            position: "absolute",
            left: i * 12 + 20,
            top: 0, bottom: 0,
            width: 1,
            background: "var(--border)",
            opacity: 0.3,
          }} />
        ))}

        {/* Chevron / spacer */}
        <span style={{ width: 14, flexShrink: 0, display: "flex", alignItems: "center" }}>
          {isFolder && (
            <ChevronRight
              size={12}
              style={{
                transform: node.isOpen ? "rotate(90deg)" : "",
                transition: "transform 0.1s",
                color: "var(--text-inactive)",
              }}
            />
          )}
        </span>

        {/* Icon */}
        <span style={{ fontSize: 12, width: 16, flexShrink: 0, lineHeight: 1 }}>
          {isFolder
            ? <Folder size={13} style={{ color: "#e3b341" }} />
            : <span style={{ color: fileColour(node.name), fontFamily: "var(--font-mono)", fontSize: 11 }}>
                {getFileIcon(node.name)}
              </span>
          }
        </span>

        {/* Name */}
        <span style={{
          flex: 1, minWidth: 0, overflow: "hidden",
          textOverflow: "ellipsis", whiteSpace: "nowrap",
          fontSize: 13, color: "var(--text-primary)",
        }}>
          {node.name}
        </span>

        {/* Context menu trigger */}
        <div className="file-item-actions">
          <button
            className="icon-btn"
            style={{ width: 16, height: 16 }}
            onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
          >
            <MoreHorizontal size={12} />
          </button>
        </div>
      </div>

      {/* Context menu */}
      {menuOpen && (
        <div
          style={{
            position: "absolute",
            right: 4,
            top: 24,
            zIndex: 50,
            width: 160,
            background: "#252526",
            border: "1px solid var(--border)",
            borderRadius: 4,
            boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
            overflow: "hidden",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {isFolder && (
            <>
              <button className="file-ctx-btn" onClick={() => { onCreatePath("file", node.path); setMenuOpen(false); }}>
                <FilePlus2 size={12} style={{ color: "var(--accent-teal)" }} />
                New File
              </button>
              <button className="file-ctx-btn" onClick={() => { onCreatePath("folder", node.path); setMenuOpen(false); }}>
                <FolderPlus size={12} style={{ color: "var(--accent-teal)" }} />
                New Folder
              </button>
              <div style={{ height: 1, background: "var(--border)", margin: "2px 0" }} />
            </>
          )}
          <button
            className="file-ctx-btn"
            style={{ color: "var(--accent-red)" }}
            onClick={() => { onDeletePath(node); setMenuOpen(false); }}
          >
            <Trash2 size={12} />
            Delete
          </button>
        </div>
      )}

      {/* Children */}
      {isFolder && node.isOpen && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeItem
              key={child.id} node={child} depth={depth + 1}
              onFileSelect={onFileSelect} onToggleFolder={onToggleFolder}
              onDeletePath={onDeletePath} onCreatePath={onCreatePath}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Filter helper ───────────────────────────────────────────────── */
function filterTree(nodes: FileNode[], q: string): FileNode[] {
  if (!q.trim()) return nodes;
  const lower = q.toLowerCase();
  return nodes.flatMap((n) => {
    if (n.type === "file") return n.name.toLowerCase().includes(lower) ? [n] : [];
    const children = filterTree(n.children || [], q);
    if (n.name.toLowerCase().includes(lower) || children.length)
      return [{ ...n, children, isOpen: true }];
    return [];
  });
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
export default function Sidebar() {
  const { files, setFiles, upsertTab, isLeftSidebarOpen, setStatusText } = useAppStore();
  const [q, setQ] = useState("");

  const visible = useMemo(() => filterTree(files, q), [files, q]);

  const reload = async () => setFiles(buildFileTree(await fileAPI.listFiles()));

  const handleFileSelect = async (node: FileNode) => {
    if (node.type !== "file") return;
    try {
      const content = await fileAPI.readFile(node.path);
      upsertTab({ id: node.id, name: node.name, path: node.path, content, language: getLanguageFromFileName(node.name), isDirty: false });
      setStatusText(`Opened ${node.path}`);
    } catch (e) { setStatusText(`Failed: ${e instanceof Error ? e.message : e}`); }
  };

  const handleToggleFolder = (node: FileNode) => {
    const toggle = (items: FileNode[]): FileNode[] =>
      items.map((i) => i.id === node.id
        ? { ...i, isOpen: !i.isOpen }
        : { ...i, children: i.children ? toggle(i.children) : i.children }
      );
    setFiles(toggle(files));
  };

  const handleCreate = async (type: "file" | "folder", base?: string) => {
    const suggested = base ? `${base}/${type === "file" ? "new-file.txt" : "new-folder"}` : "";
    const path = window.prompt(`New ${type} path:`, suggested)?.trim();
    if (!path) return;
    try {
      await fileAPI.createPath(path, type, "");
      await reload();
      setStatusText(`Created ${path}`);
    } catch (e) { setStatusText(`Create failed: ${e instanceof Error ? e.message : e}`); }
  };

  const handleDelete = async (node: FileNode) => {
    if (!window.confirm(`Delete ${node.path}?`)) return;
    try {
      await fileAPI.deleteFile(node.path);
      await reload();
      setStatusText(`Deleted ${node.path}`);
    } catch (e) { setStatusText(`Delete failed: ${e instanceof Error ? e.message : e}`); }
  };

  if (!isLeftSidebarOpen) return null;

  return (
    <div className="sidebar">
      {/* Header */}
      <div className="sidebar-section-header">
        <span>Explorer</span>
        <div className="sidebar-actions">
          <button className="sidebar-action-btn" title="New File" onClick={() => void handleCreate("file")}>
            <FilePlus2 size={13} />
          </button>
          <button className="sidebar-action-btn" title="New Folder" onClick={() => void handleCreate("folder")}>
            <FolderPlus size={13} />
          </button>
          <button className="sidebar-action-btn" title="Refresh" onClick={() => void reload()}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="sidebar-search" style={{ position: "relative" }}>
        <Search className="sidebar-search-icon" size={12} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search files…"
        />
      </div>

      {/* Tree */}
      <div className="file-tree">
        {visible.length === 0
          ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 120, color: "var(--text-inactive)", fontSize: 12, gap: 6 }}>
              <Folder size={24} style={{ opacity: 0.3 }} />
              {q ? "No matches" : "Workspace is empty"}
            </div>
          )
          : visible.map((n) => (
            <FileTreeItem
              key={n.id} node={n} depth={0}
              onFileSelect={handleFileSelect}
              onToggleFolder={handleToggleFolder}
              onDeletePath={handleDelete}
              onCreatePath={handleCreate}
            />
          ))
        }
      </div>

      {/* Footer */}
      <div style={{
        borderTop: "1px solid var(--border)",
        padding: "4px 12px",
        fontSize: 11,
        color: "var(--text-inactive)",
        flexShrink: 0,
      }}>
        {files.length} items · workspace
      </div>

      {/* Inline style for context menu buttons */}
      <style>{`
        .file-ctx-btn {
          display: flex; align-items: center; gap: 7px;
          width: 100%; padding: 6px 10px;
          font-size: 12px; color: var(--text-primary);
          background: transparent; border: none; cursor: pointer;
          text-align: left; transition: background 0.1s;
        }
        .file-ctx-btn:hover { background: var(--bg-hover); }
      `}</style>
    </div>
  );
}
