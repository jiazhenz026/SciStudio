/**
 * #2378 — the Bring In My Work dialog closes from an icon-only X in its header.
 */
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CLAUDE, ready, renderDialog, settled } from "./BringInMyWorkDialog.harness";

afterEach(cleanup);

describe("Bring In My Work header close control (#2378)", () => {
  it("is an icon-only X that closes the dialog", async () => {
    const { onClose } = renderDialog(ready(CLAUDE));
    await settled();

    const close = screen.getByTestId("work-import-close");
    expect(close.textContent).toBe("");
    expect(close).toHaveAccessibleName("Close");
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
