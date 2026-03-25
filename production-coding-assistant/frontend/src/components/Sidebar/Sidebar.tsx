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
  const indent = depth * 14 + 10;
  const isFolder = node.type === "folder";

  return (
    <div className="relative isolate">
      {/* Row */}
      <div
        className="group flex items-center gap-1.5 h-6 pr-2 cursor-pointer text-[13px] text-zinc-300 border border-transparent hover:bg-[#18181b]/80 hover:text-white"
        style={{ paddingLeft: indent }}
        onClick={() => isFolder ? onToggleFolder(node) : onFileSelect(node)}
      >
        {/* Indent guide lines */}
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} className="absolute top-0 bottom-0 w-px bg-zinc-800" style={{ left: i * 14 + 20 }} />
        ))}

        {/* Chevron / spacer */}
        <span className="w-4 shrink-0 flex items-center justify-center">
          {isFolder && (
            <ChevronRight
              size={13}
              style={{
                transform: node.isOpen ? "rotate(90deg)" : "",
                transition: "transform 0.15s ease",
              }}
              className="text-zinc-500 group-hover:text-zinc-300"
            />
          )}
        </span>

        {/* Icon */}
        <span className="text-[12px] w-4 shrink-0 flex items-center leading-none">
          {isFolder
            ? <Folder size={14} className="text-amber-500/90" />
            : <span style={{ color: fileColour(node.name) }} className="font-mono text-[11px] drop-shadow-sm">
                {getFileIcon(node.name)}
              </span>
          }
        </span>

        {/* Name */}
        <span className="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap tracking-wide">
          {node.name}
        </span>

        {/* Context menu trigger */}
        <div className="hidden group-hover:flex items-center gap-0.5 ml-auto pr-1">
          <button
            className="w-5 h-5 flex flex-col items-center justify-center rounded pl-0.5 text-zinc-400 hover:text-white hover:bg-zinc-700/50 transition-colors"
            onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
          >
            <MoreHorizontal size={14} />
          </button>
        </div>
      </div>

      {/* Context menu */}
      {menuOpen && (
        <div
          className="absolute right-1 top-6 z-50 w-40 bg-zinc-900 border border-zinc-700 shadow-[0_8px_32px_rgba(0,0,0,0.8)] rounded-md overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {isFolder && (
            <>
              <button 
                className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-zinc-200 bg-transparent border-none cursor-pointer text-left hover:bg-zinc-800 transition-colors"
                onClick={() => { onCreatePath("file", node.path); setMenuOpen(false); }}
              >
                <FilePlus2 size={13} className="text-teal-400" />
                New File
              </button>
              <button 
                className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-zinc-200 bg-transparent border-none cursor-pointer text-left hover:bg-zinc-800 transition-colors"
                onClick={() => { onCreatePath("folder", node.path); setMenuOpen(false); }}
              >
                <FolderPlus size={13} className="text-teal-400" />
                New Folder
              </button>
              <div className="h-px bg-zinc-800 my-0.5" />
            </>
          )}
          <button
            className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-red-400 bg-transparent border-none cursor-pointer text-left hover:bg-red-950/40 hover:text-red-300 transition-colors"
            onClick={() => { onDeletePath(node); setMenuOpen(false); }}
          >
            <Trash2 size={13} />
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
    <div className="w-[260px] shrink-0 flex flex-col bg-[#0f0f11] border-r border-[#27272a] overflow-hidden drop-shadow-md z-10 relative">
      {/* Header */}
      <div className="group flex items-center justify-between px-3 py-2 text-[11px] font-bold uppercase tracking-[0.08em] text-zinc-500 shrink-0">
        <span className="mt-1">Explorer</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button className="w-6 h-6 flex items-center justify-center rounded text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors" title="New File" onClick={() => void handleCreate("file")}>
            <FilePlus2 size={14} />
          </button>
          <button className="w-6 h-6 flex items-center justify-center rounded text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors" title="New Folder" onClick={() => void handleCreate("folder")}>
            <FolderPlus size={14} />
          </button>
          <button className="w-6 h-6 flex items-center justify-center rounded text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors" title="Refresh" onClick={() => void reload()}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 pb-2 shrink-0 relative">
        <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none mt-[-4px]" size={13} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search files…"
          className="w-full h-7 bg-zinc-900/80 border border-zinc-800 rounded placeholder-zinc-600 focus:outline-none focus:border-blue-500/50 focus:bg-zinc-900 transition-colors pl-7 pr-2 text-xs text-zinc-200 font-sans shadow-inner"
        />
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto py-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-zinc-800 [&::-webkit-scrollbar-track]:bg-transparent hover:[&::-webkit-scrollbar-thumb]:bg-zinc-700">
        {visible.length === 0
          ? (
            <div className="flex flex-col items-center justify-center h-28 text-zinc-600 text-xs gap-2">
              <Folder size={28} className="opacity-20" strokeWidth={1.5} />
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
      <div className="border-t border-zinc-800/60 px-3 py-1.5 text-[10px] uppercase tracking-widest text-zinc-600 shrink-0 font-bold">
        {files.length} items
      </div>
    </div>
  );
}
