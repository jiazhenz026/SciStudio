/**
 * Monaco custom theme — extracted in #1413 to keep the CodeEditor function
 * under the 150-line limit. Pure-data definition; the registration call
 * lives in CodeEditor.handleBeforeMount.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function defineSoftDarkTheme(monaco: any) {
  // SPIKE: soft-dark theme (One Dark-ish warm palette, lower contrast than vs-dark).
  monaco.editor.defineTheme("scistudio-soft-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [],
    colors: {
      "editor.background": "#282c34",
      "editor.foreground": "#abb2bf",
      "editorLineNumber.foreground": "#4b5263",
      "editorLineNumber.activeForeground": "#abb2bf",
      "editor.selectionBackground": "#3e4452",
      "editor.inactiveSelectionBackground": "#3e445280",
      "editorCursor.foreground": "#56b6c2",
      "editor.lineHighlightBackground": "#2c313a",
      "editorIndentGuide.background": "#3b4048",
      "editorIndentGuide.activeBackground": "#5c6370",
      "editorWhitespace.foreground": "#3b4048",
      "editorBracketMatch.background": "#3e4452",
      "editorBracketMatch.border": "#56b6c2",
    },
  });
}
