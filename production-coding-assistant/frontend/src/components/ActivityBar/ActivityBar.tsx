import { Bot, Files, Settings2, TerminalSquare } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";

const ITEMS = [
  { id: "explorer", label: "Explorer", icon: Files },
  { id: "assistant", label: "AI Chat",  icon: Bot },
  { id: "terminal", label: "Terminal",  icon: TerminalSquare },
];

export default function ActivityBar() {
  const {
    isLeftSidebarOpen,
    isRightPanelOpen,
    isBottomPanelOpen,
    toggleLeftSidebar,
    toggleRightPanel,
    toggleBottomPanel,
    toggleSettings,
  } = useAppStore();

  const isActive = (id: string) => {
    if (id === "explorer") return isLeftSidebarOpen;
    if (id === "assistant") return isRightPanelOpen;
    if (id === "terminal") return isBottomPanelOpen;
    return false;
  };

  const handleClick = (id: string) => {
    if (id === "explorer") toggleLeftSidebar();
    else if (id === "assistant") toggleRightPanel();
    else if (id === "terminal") toggleBottomPanel();
  };

  return (
    <div className="w-12 shrink-0 flex flex-col items-center justify-between bg-[#121214] border-r border-[#27272a] py-2 z-20 shadow-[1px_0_10px_rgba(0,0,0,0.3)]">
      <div className="flex flex-col items-center w-full gap-2">
        {ITEMS.map(({ id, label, icon: Icon }) => {
          const active = isActive(id);
          return (
            <button
              key={id}
              onClick={() => handleClick(id)}
              className="relative w-12 h-12 flex items-center justify-center text-zinc-500 hover:text-zinc-200 transition-colors bg-transparent border-none cursor-pointer group"
              title={label}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-7 bg-blue-500 rounded-r-md" />
              )}
              <Icon size={22} strokeWidth={active ? 2 : 1.5} className={active ? "text-zinc-100 drop-shadow-[0_0_8px_rgba(255,255,255,0.3)]" : "group-hover:scale-110 transition-transform"} />
            </button>
          );
        })}
      </div>

      <div className="flex flex-col items-center w-full">
        <button
          onClick={toggleSettings}
          className="relative w-12 h-12 flex items-center justify-center text-zinc-500 hover:text-zinc-200 transition-all hover:scale-110 bg-transparent border-none cursor-pointer"
          title="Settings"
        >
          <Settings2 size={22} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
