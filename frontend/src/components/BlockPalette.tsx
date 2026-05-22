import { useRef, useState } from "react";

import type { BlockSummary } from "../types/api";

interface BlockPaletteProps {
  blocks: BlockSummary[];
  search: string;
  collapsed: boolean;
  onSearch: (value: string) => void;
  onReload: () => void;
  onAddBlock: (block: BlockSummary) => void;
}

/**
 * Derive the display package name for a block.
 *
 * Priority:
 *   1. block.package_name (explicit backend field)
 *   2. prefix before the first dot in type_name (e.g. "Imaging" from "imaging.cellpose_segment")
 *      Short prefixes (≤4 chars) are uppercased (e.g. "LCMS", "SRS").
 *   3. "SciStudio Core" for blocks with source === "builtin" or no dot in type_name
 *   4. "Custom" for blocks with source === "custom"
 */
function derivePackage(block: BlockSummary): string {
  if (block.package_name) {
    return block.package_name;
  }
  if (block.source === "custom") {
    return "Custom";
  }
  const dotIndex = block.type_name.indexOf(".");
  if (dotIndex > 0) {
    const prefix = block.type_name.slice(0, dotIndex);
    // Uppercase short acronym-like prefixes (≤4 chars), otherwise title-case.
    if (prefix.length <= 4) {
      return prefix.toUpperCase();
    }
    return prefix.charAt(0).toUpperCase() + prefix.slice(1);
  }
  return "SciStudio Core";
}

interface BlockCardProps {
  block: BlockSummary;
  collapsed: boolean;
  onDragStart: (event: React.DragEvent, block: BlockSummary) => void;
  onAddBlock: (block: BlockSummary) => void;
  index: number;
}

function BlockCard({ block, collapsed, onDragStart, onAddBlock, index }: BlockCardProps) {
  return (
    <div
      className="rounded-[1.4rem] border border-stone-200 bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:border-ember"
      draggable
      key={`${block.type_name}-${block.name}-${index}`}
      onDragStart={(event) => onDragStart(event, block)}
    >
      <button className="w-full text-left" onClick={() => onAddBlock(block)} type="button">
        <p className="font-medium text-ink">{collapsed ? block.name.slice(0, 2) : block.name}</p>
        {collapsed ? null : (
          <>
            <p className="mt-1 text-xs text-stone-500">{block.description}</p>
            <p className="mt-2 text-[11px] uppercase tracking-[0.25em] text-stone-500">
              {block.input_ports.length} in / {block.output_ports.length} out
            </p>
          </>
        )}
      </button>
    </div>
  );
}

interface CategorySectionProps {
  category: string;
  blocks: BlockSummary[];
  paletteCollapsed: boolean;
  onDragStart: (event: React.DragEvent, block: BlockSummary) => void;
  onAddBlock: (block: BlockSummary) => void;
}

function CategorySection({
  category,
  blocks,
  paletteCollapsed,
  onDragStart,
  onAddBlock,
}: CategorySectionProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div>
      {paletteCollapsed ? null : (
        <button
          className="mb-1 flex w-full items-center gap-1 text-left"
          onClick={() => setIsCollapsed((prev) => !prev)}
          type="button"
        >
          <span className="text-[10px] text-stone-500">{isCollapsed ? "▶" : "▼"}</span>
          <span className="rounded-md border border-stone-300 bg-stone-100 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.25em] text-stone-600">
            {category}
          </span>
        </button>
      )}
      {isCollapsed && !paletteCollapsed ? null : (
        <div className="space-y-2 pl-2">
          {blocks.map((block, index) => (
            <BlockCard
              block={block}
              collapsed={paletteCollapsed}
              index={index}
              key={`${block.type_name}-${block.name}-${index}`}
              onAddBlock={onAddBlock}
              onDragStart={onDragStart}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PackageSectionProps {
  packageName: string;
  categories: { category: string; blocks: BlockSummary[] }[];
  paletteCollapsed: boolean;
  onDragStart: (event: React.DragEvent, block: BlockSummary) => void;
  onAddBlock: (block: BlockSummary) => void;
}

function PackageSection({
  packageName,
  categories,
  paletteCollapsed,
  onDragStart,
  onAddBlock,
}: PackageSectionProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <section>
      {paletteCollapsed ? null : (
        <button
          className="mb-2 flex w-full items-center gap-1 text-left"
          onClick={() => setIsCollapsed((prev) => !prev)}
          type="button"
        >
          <span className="text-[11px] text-stone-600">{isCollapsed ? "▶" : "▼"}</span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.3em] text-stone-700">
            {packageName}
          </span>
        </button>
      )}
      {isCollapsed && !paletteCollapsed ? null : (
        <div className="space-y-3">
          {categories.map(({ category, blocks }) => (
            <CategorySection
              blocks={blocks}
              category={category}
              key={category}
              onAddBlock={onAddBlock}
              onDragStart={onDragStart}
              paletteCollapsed={paletteCollapsed}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Build a 3-level grouping: package → category → blocks.
 *
 * - "Custom" package sorts to the bottom.
 * - Other packages sort alphabetically.
 * - Categories within a package sort alphabetically.
 * - Blocks within a category sort alphabetically by name.
 * - Empty categories/packages are excluded (guaranteed by the filter caller).
 */
function groupBlocks(blocks: BlockSummary[]): {
  packageName: string;
  categories: { category: string; blocks: BlockSummary[] }[];
}[] {
  const packageMap = new Map<string, Map<string, BlockSummary[]>>();

  for (const block of blocks) {
    const pkg = derivePackage(block);
    const cat = block.subcategory || block.base_category || "general";

    if (!packageMap.has(pkg)) {
      packageMap.set(pkg, new Map());
    }
    const catMap = packageMap.get(pkg)!;
    if (!catMap.has(cat)) {
      catMap.set(cat, []);
    }
    catMap.get(cat)!.push(block);
  }

  const sorted = [...packageMap.keys()].sort((a, b) => {
    if (a === "Custom") return 1;
    if (b === "Custom") return -1;
    return a.localeCompare(b);
  });

  return sorted.map((pkg) => {
    const catMap = packageMap.get(pkg)!;
    const categories = [...catMap.keys()]
      .sort((a, b) => a.localeCompare(b))
      .map((cat) => ({
        category: cat,
        blocks: [...catMap.get(cat)!].sort((a, b) => a.name.localeCompare(b.name)),
      }));
    return { packageName: pkg, categories };
  });
}

export function BlockPalette({
  blocks,
  search,
  collapsed,
  onSearch,
  onReload,
  onAddBlock,
}: BlockPaletteProps) {
  const dragImageRef = useRef<HTMLDivElement | null>(null);

  // When a search query is active, auto-expand all matching branches by filtering
  // to only blocks that match. groupBlocks then produces only the non-empty groups.
  const filtered = blocks.filter((block) => {
    const value =
      `${block.name} ${block.description} ${block.subcategory || block.base_category}`.toLowerCase();
    return value.includes(search.toLowerCase());
  });

  const grouped = groupBlocks(filtered);

  const handleDragStart = (event: React.DragEvent, block: BlockSummary) => {
    const payload = { ...block };
    if (block.direction) {
      (payload as Record<string, unknown>)._default_direction = block.direction;
    }
    event.dataTransfer.setData("application/scistudio-block", JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";

    if (dragImageRef.current) {
      dragImageRef.current.textContent = block.name;
      dragImageRef.current.style.display = "block";
      event.dataTransfer.setDragImage(dragImageRef.current, 40, 16);
      requestAnimationFrame(() => {
        if (dragImageRef.current) dragImageRef.current.style.display = "none";
      });
    }
  };

  return (
    <aside className="flex h-full flex-col overflow-hidden border-r border-stone-200 bg-[linear-gradient(180deg,_rgba(255,255,255,0.95),_rgba(245,241,232,0.98))] p-4">
      {/* Drag ghost element (offscreen) */}
      <div
        ref={dragImageRef}
        className="pointer-events-none fixed -left-[9999px] -top-[9999px] rounded-xl border border-ember bg-white px-4 py-2 text-sm font-medium text-ink shadow-lg"
        style={{ display: "none" }}
      />

      <div className="flex items-center justify-between gap-2">
        {collapsed ? null : <p className="font-display text-xl text-ink">Palette</p>}
        <button className="toolbar-button" onClick={onReload} type="button">
          {collapsed ? "\u21BB" : "Reload"}
        </button>
      </div>

      {collapsed ? null : (
        <input
          className="mt-4 w-full rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-ember"
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search blocks"
          value={search}
        />
      )}

      <div className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto pb-6 scrollbar-thin">
        {grouped.map(({ packageName, categories }) => (
          <PackageSection
            categories={categories}
            key={packageName}
            onAddBlock={onAddBlock}
            onDragStart={handleDragStart}
            packageName={packageName}
            paletteCollapsed={collapsed}
          />
        ))}
      </div>
    </aside>
  );
}
