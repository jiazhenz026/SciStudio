// Extracted from BlockNode.tsx as part of the #1422 god-file split.
//
// InlineConfigField — discriminator that renders the right widget for each
// `ConfigProperty` exposed in the BlockNode inline-config strip. Each
// widget branch lives in its own sub-component (mostly to keep this
// discriminator's cyclomatic complexity below the eslint cap), and the
// default text-input case is delegated to `InlineTextInputField` so its
// hook chain sits at the top level of its own component — that is the
// Wave 1 (#1420) rules-of-hooks fix and MUST be preserved through this
// split.

import { InlineTextInputField } from "./InlineTextInputField";
import type { ConfigProperty } from "./inlineConfigHelpers";

type OnChangeFn = (key: string, val: unknown) => void;

function fieldLabel(prop: ConfigProperty): string {
  return (prop.schema.title as string) ?? prop.key;
}

function InlineEnumField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: OnChangeFn;
}) {
  const { key, schema } = prop;
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-stone-500">{fieldLabel(prop)}</span>
      <select
        className="nodrag nowheel min-w-0 flex-1 truncate rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
        value={String(value ?? schema.default ?? "")}
        onChange={(e) => onChange(key, e.target.value)}
      >
        {(schema.enum as unknown[]).map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {String(opt)}
          </option>
        ))}
      </select>
    </label>
  );
}

function InlineBooleanField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: OnChangeFn;
}) {
  const { key, schema } = prop;
  const checked = (value ?? schema.default ?? false) as boolean;
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-stone-500">{fieldLabel(prop)}</span>
      <input
        type="checkbox"
        className="nodrag nowheel h-4 w-4 accent-sea"
        checked={checked}
        onChange={(e) => onChange(key, e.target.checked)}
      />
    </label>
  );
}

function InlineNumberField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: OnChangeFn;
}) {
  const { key, schema } = prop;
  const inputValue =
    value === null || value === undefined ? String(schema.default ?? "") : String(value);
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="shrink-0 text-stone-500">{fieldLabel(prop)}</span>
      <input
        type="number"
        className="nodrag nowheel min-w-0 flex-1 rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
        value={inputValue}
        onChange={(e) => {
          const num = Number(e.target.value);
          onChange(key, Number.isNaN(num) ? e.target.value : num);
        }}
      />
    </label>
  );
}

function InlineTextareaField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: OnChangeFn;
}) {
  const { key, schema } = prop;
  const label = fieldLabel(prop);
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="text-stone-500">{label}</span>
      <textarea
        className="nodrag nowheel w-full resize-y rounded border border-stone-200 bg-white px-2 py-1 text-xs text-ink focus:border-sea focus:outline-none"
        rows={6}
        placeholder={`Enter ${label.toLowerCase()}...`}
        value={String(value ?? schema.default ?? "")}
        onChange={(e) => onChange(key, e.target.value)}
      />
    </label>
  );
}

export function InlineConfigField({
  prop,
  value,
  onChange,
}: {
  prop: ConfigProperty;
  value: unknown;
  onChange: OnChangeFn;
}) {
  const { schema } = prop;

  if (Array.isArray(schema.enum)) {
    return <InlineEnumField prop={prop} value={value} onChange={onChange} />;
  }
  if (schema.type === "boolean") {
    return <InlineBooleanField prop={prop} value={value} onChange={onChange} />;
  }
  if (schema.type === "number" || schema.type === "integer") {
    return <InlineNumberField prop={prop} value={value} onChange={onChange} />;
  }
  if ((schema.ui_widget as string | undefined) === "textarea") {
    return <InlineTextareaField prop={prop} value={value} onChange={onChange} />;
  }

  // Default: text input — delegated to a dedicated sub-component so its
  // Hooks (useState/useRef/useLayoutEffect) sit at the top level rather than
  // after the early returns above. Splitting the default branch into its own
  // component preserves the prior behavior while satisfying
  // react-hooks/rules-of-hooks (#1420).
  return <InlineTextInputField prop={prop} value={value} onChange={onChange} />;
}
