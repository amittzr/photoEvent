"use client";

import type { Folder } from "@/lib/types";

interface FolderTabsProps {
  folders: Folder[];
  activeId: string | null;
  onSelect: (folderId: string) => void;
}

// Horizontal, scrollable folder/category tabs.
export default function FolderTabs({
  folders,
  activeId,
  onSelect,
}: FolderTabsProps) {
  return (
    <nav className="scrollbar-hide -mx-4 flex gap-2 overflow-x-auto px-4 py-2">
      {folders.map((folder) => {
        const active = folder.id === activeId;
        return (
          <button
            key={folder.id}
            type="button"
            onClick={() => onSelect(folder.id)}
            className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition ${
              active
                ? "bg-brand text-white"
                : "bg-white text-neutral-700 hover:bg-neutral-100"
            }`}
          >
            {folder.name}
            <span
              className={`ml-2 text-xs ${
                active ? "text-white/80" : "text-neutral-400"
              }`}
            >
              {folder.photo_count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
