import { useMemo, useState } from "react";
import {
  ChevronRight, FilePlus2, FolderPlus, RefreshCw,
  Search, Trash2, MoreHorizontal, Folder, FolderOpen
} from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { fileAPI, settingsAPI } from "../../utils/api";
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
    <div className="relative isolate mb-0.5">
      {/* Row */}
      <div
        className="group flex items-center gap-1.5 h-7 mx-1 pr-2 rounded-md cursor-pointer text-[13px] text-zinc-400 border border-transparent hover:bg-zinc-800/60 hover:text-zinc-100 transition-colors"
        style={{ paddingLeft: indent - 8 }}
        onClick={() => isFolder ? onToggleFolder(node) : onFileSelect(node)}
      >
        {/* Indent guide lines */}
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} className="absolute top-0 bottom-0 w-px bg-zinc-800/40 group-hover:bg-zinc-700/60" style={{ left: i * 14 + 18 }} />
        ))}

        {/* Chevron / spacer */}
        <span className="w-4 shrink-0 flex items-center justify-center">
          {isFolder && (
            <ChevronRight
              size={14}
              style={{
                transform: node.isOpen ? "rotate(90deg)" : "",
                transition: "transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
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
        <div className="hidden group-hover:flex items-center ml-auto pl-2">
          <button
            className="w-6 h-6 flex items-center justify-center rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-700/80 transition-all opacity-0 group-hover:opacity-100 translate-x-1 group-hover:translate-x-0"
            onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
          >
            <MoreHorizontal size={15} />
          </button>
        </div>
      </div>

      {/* Context menu */}
      {menuOpen && (
        <>
        <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
        <div
          className="absolute right-4 top-7 z-50 w-44 bg-zinc-900 border border-zinc-800/80 shadow-2xl rounded-lg overflow-hidden py-1 backdrop-blur-xl"
          onClick={(e) => e.stopPropagation()}
        >
          {isFolder && (
            <>
              <button 
                className="flex items-center gap-3 w-full px-3 py-2.5 text-[13px] font-medium text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                onClick={() => { onCreatePath("file", node.path); setMenuOpen(false); }}
              >
                <FilePlus2 size={14} className="text-blue-400" />
                New File
              </button>
              <button 
                className="flex items-center gap-3 w-full px-3 py-2.5 text-[13px] font-medium text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
                onClick={() => { onCreatePath("folder", node.path); setMenuOpen(false); }}
              >
                <FolderPlus size={14} className="text-amber-400" />
                New Folder
              </button>
              <div className="h-px bg-zinc-800/60 my-1 mx-2" />
            </>
          )}
          <button
            className="flex items-center gap-3 w-full px-3 py-2.5 text-[13px] font-medium text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
            onClick={() => { onDeletePath(node); setMenuOpen(false); }}
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
        </>
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

  const handleOpenFolder = async () => {
    let path: string | null = null;
    if (window.desktopBridge) {
      try {
        path = await window.desktopBridge.selectFolder();
      } catch {
        setStatusText("Folder selection failed.");
        return;
      }
    } else {
      path = window.prompt("Enter the absolute path to the workspace folder:")?.trim() || null;
    }
    if (!path) return;
    try {
      await settingsAPI.save({ workspacePath: path } as any);
      await reload();
      setStatusText(`Opened workspace: ${path}`);
    } catch (e) {
      setStatusText(`Failed to open folder: ${e instanceof Error ? e.message : e}`);
    }
  };

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
    <div className="w-[260px] shrink-0 flex flex-col bg-[#0f0f11] border-r border-[#27272a] overflow-hidden drop-shadow-md z-[1] relative">
      {/* Header */}
      <div className="group flex items-center justify-between px-4 py-3 text-xs font-bold uppercase tracking-[0.1em] text-zinc-500 shrink-0">
        <span className="mt-0.5">Explorer</span>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button className="w-6 h-6 flex items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors transform hover:scale-105" title="New File" onClick={() => void handleCreate("file")}>
            <FilePlus2 size={15} />
          </button>
          <button className="w-6 h-6 flex items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors transform hover:scale-105" title="New Folder" onClick={() => void handleCreate("folder")}>
            <FolderPlus size={15} />
          </button>
          <button className="w-6 h-6 flex items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100 transition-colors transform hover:scale-105" title="Refresh" onClick={() => void reload()}>
            <RefreshCw size={14} />
          </button>
          <button className="w-6 h-6 flex items-center justify-center rounded-md text-blue-400 hover:bg-blue-500/20 hover:text-blue-300 transition-colors transform hover:scale-105 ml-0.5" title="Open Folder..." onClick={() => void handleOpenFolder()}>
            <FolderOpen size={15} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 pb-3 shrink-0 relative">
        <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none mt-[2px]" size={14} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search files…"
          className="w-full h-8 bg-zinc-900/50 border border-zinc-800/80 rounded-lg placeholder-zinc-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 focus:bg-zinc-900 transition-all pl-9 pr-3 text-[13px] text-zinc-200 font-sans shadow-sm"
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
