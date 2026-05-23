/**
 * The form fields (name / path / description / Browse) inside ProjectDialog.
 *
 * Extracted in #1413 so the parent function stays under 150 lines.
 */
export interface ProjectFormFieldsProps {
  mode: "new" | "open";
  name: string;
  description: string;
  path: string;
  onChange: (patch: Partial<{ name: string; description: string; path: string }>) => void;
  onPathChangeClearError: () => void;
  onBrowse: () => void;
}

export function ProjectFormFields({
  mode,
  name,
  description,
  path,
  onChange,
  onPathChangeClearError,
  onBrowse,
}: ProjectFormFieldsProps) {
  return (
    <div className={`grid gap-4 ${mode === "new" ? "md:grid-cols-2" : ""}`}>
      <label className="grid gap-2 text-sm text-stone-700">
        <span className="font-medium">
          {mode === "new" ? "Project name" : "Project ID or path"}
        </span>
        {mode === "open" ? (
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
              onChange={(event) => {
                onChange({ path: event.target.value });
                onPathChangeClearError();
              }}
              placeholder="C:\\research\\atlas-project"
              value={path}
            />
            <button
              className="shrink-0 rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-600 transition hover:border-ember hover:text-ember"
              onClick={onBrowse}
              type="button"
            >
              Browse
            </button>
          </div>
        ) : (
          <input
            className="rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
            onChange={(event) => onChange({ name: event.target.value })}
            placeholder="Multimodal Atlas"
            value={name}
          />
        )}
      </label>
      {mode === "new" ? (
        <div className="grid gap-2 text-sm text-stone-700">
          <span className="font-medium">Parent directory</span>
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
              onChange={(event) => {
                onChange({ path: event.target.value });
                onPathChangeClearError();
              }}
              placeholder="C:\\projects"
              value={path}
            />
            <button
              className="shrink-0 rounded-2xl border border-stone-300 bg-white px-4 py-3 text-sm font-medium text-stone-600 transition hover:border-ember hover:text-ember"
              onClick={onBrowse}
              type="button"
            >
              Browse
            </button>
          </div>
        </div>
      ) : null}
      {mode === "new" ? (
        <label className="grid gap-2 text-sm text-stone-700 md:col-span-2">
          <span className="font-medium">Description</span>
          <textarea
            className="min-h-28 rounded-2xl border border-stone-300 bg-white px-4 py-3 outline-none transition focus:border-ember"
            onChange={(event) => onChange({ description: event.target.value })}
            placeholder="Integrated IF, Raman, and LC-MS pilot."
            value={description}
          />
        </label>
      ) : null}
    </div>
  );
}
