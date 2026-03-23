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
    <div className="activity-bar">
      <div className="activity-bar-top">
        {ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => handleClick(id)}
            className={`activity-btn${isActive(id) ? " active" : ""}`}
            title={label}
          >
            <Icon size={22} strokeWidth={1.5} />
          </button>
        ))}
      </div>

      <div className="activity-bar-bottom">
        <button
          onClick={toggleSettings}
          className="activity-btn"
          title="Settings"
        >
          <Settings2 size={22} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
