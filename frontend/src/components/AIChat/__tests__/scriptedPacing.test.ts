/**
 * ADR-053 FR-061a (#2083) — the scripted replay's pacing.
 *
 * The clock and the timer are injected rather than faked globally, so these
 * assertions are about the pacing arithmetic itself and never about vitest's
 * timer emulation. `advance(ms)` moves the clock and runs whatever the writer
 * scheduled, which is exactly what a browser would do.
 */
import { describe, expect, it, vi } from "vitest";

import {
  INITIAL_TOKENIZE_STATE,
  MAX_CATCHUP_MS,
  SCRIPTED_AGENT_MS_PER_CHAR,
  SCRIPTED_PARAGRAPH_PAUSE_MS,
  SCRIPTED_PROMPT_MS_PER_CHAR,
  SCRIPTED_SUBMIT_PAUSE_MS,
  createPacedWriter,
  escapeSequenceEnd,
  tokenize,
} from "../scriptedPacing";

const ESC = String.fromCharCode(27);
const BEL = String.fromCharCode(7);
/** Bold cyan, the colour the transcripts print the reader's question in. */
const CYAN = `${ESC}[36m`;
const RESET = `${ESC}[0m`;

/** A clock and a single-slot timer the test drives by hand. */
function harness(options: { instant?: boolean; box?: boolean } = {}) {
  let clock = 0;
  let pending: { fn: () => void; dueAt: number } | null = null;
  let nextHandle = 1;
  const written: string[] = [];
  /* Stands in for the agent window's prompt box. */
  let typed = "";
  const submits: string[] = [];

  const writer = createPacedWriter({
    write: (data) => written.push(data),
    instant: options.instant ?? false,
    promptSink: options.box
      ? {
          onType: (text) => {
            typed += text;
          },
          onSubmit: () => {
            submits.push(typed);
            typed = "";
          },
        }
      : undefined,
    now: () => clock,
    setTimer: (fn, ms) => {
      pending = { fn, dueAt: clock + ms };
      return nextHandle++;
    },
    clearTimer: () => {
      pending = null;
    },
  });

  /** Move the clock forward, firing every timer that comes due on the way. */
  const advance = (ms: number): void => {
    const target = clock + ms;
    // The writer re-arms inside its own callback, so this loop keeps firing
    // until nothing else is due before `target`.
    for (let guard = 0; guard < 10_000; guard += 1) {
      if (pending === null || pending.dueAt > target) break;
      clock = Math.max(clock, pending.dueAt);
      const due = pending;
      pending = null;
      due.fn();
    }
    clock = target;
  };

  /**
   * What a backgrounded tab does: the clock jumps, and the timer that should
   * have fired many times over fires exactly once, very late.
   */
  const jumpAndFire = (ms: number): void => {
    clock += ms;
    const due = pending;
    pending = null;
    due?.fn();
  };

  return {
    writer,
    written,
    advance,
    jumpAndFire,
    text: () => written.join(""),
    box: () => typed,
    submits,
    hasPendingTimer: () => pending !== null,
  };
}

describe("escapeSequenceEnd (#2083)", () => {
  it("takes a CSI sequence up to and including its final byte", () => {
    const data = `${ESC}[1;36mX`;
    expect(escapeSequenceEnd(data, 0)).toBe(data.indexOf("m") + 1);
  });

  it("takes an OSC sequence terminated by BEL", () => {
    const data = `${ESC}]0;title${BEL}rest`;
    expect(data.slice(0, escapeSequenceEnd(data, 0))).toBe(`${ESC}]0;title${BEL}`);
  });

  it("takes an OSC sequence terminated by ST", () => {
    const data = `${ESC}]0;title${ESC}\\rest`;
    expect(data.slice(0, escapeSequenceEnd(data, 0))).toBe(`${ESC}]0;title${ESC}\\`);
  });

  it("takes the two-byte form for anything else", () => {
    expect(escapeSequenceEnd(`${ESC}Mrest`, 0)).toBe(2);
  });

  it("reports -1 when the chunk ends mid-sequence", () => {
    expect(escapeSequenceEnd(`${ESC}[1;36`, 0)).toBe(-1);
    expect(escapeSequenceEnd(ESC, 0)).toBe(-1);
  });
});

describe("tokenize (#2083)", () => {
  /* A bare paced terminal: no prompt box, so the question is typed into it. */
  const opts = {
    agentMsPerChar: 10,
    promptMsPerChar: 50,
    paragraphPauseMs: 100,
    submitPauseMs: 500,
    splitPrompt: false,
    ...INITIAL_TOKENIZE_STATE,
  };
  /* The agent window: the question goes to the box instead. */
  const split = { ...opts, splitPrompt: true };

  it("charges one character at a time and nothing for colour", () => {
    const { tokens } = tokenize(`${CYAN}ab${RESET}`, opts);
    expect(tokens).toEqual([
      { text: CYAN, delayMs: 0, channel: "agent" },
      { text: "a", delayMs: 10, channel: "agent" },
      { text: "b", delayMs: 10, channel: "agent" },
      { text: RESET, delayMs: 0, channel: "agent" },
    ]);
  });

  it("charges the extra pause only on the newline that closes a blank line", () => {
    const { tokens } = tokenize("a\n\nb", opts);
    expect(tokens.map((t) => t.delayMs)).toEqual([10, 10, 110, 10]);
  });

  it("recognises a blank line straddling two chunks", () => {
    const first = tokenize("a\n", opts);
    expect(first.state.lastVisible).toBe("\n");
    const second = tokenize("\nb", { ...opts, ...first.state });
    expect(second.tokens[0].delayMs).toBe(110);
  });

  it("charges nothing for a carriage return", () => {
    const { tokens } = tokenize("\r", opts);
    expect(tokens).toEqual([{ text: "\r", delayMs: 0, channel: "agent" }]);
  });

  it("carries a truncated escape sequence instead of emitting it", () => {
    const { tokens, carry } = tokenize(`a${ESC}[1`, opts);
    expect(tokens).toEqual([{ text: "a", delayMs: 10, channel: "agent" }]);
    expect(carry).toBe(`${ESC}[1`);
  });

  describe("two voices", () => {
    it("types a `>` line at the reader's pace and the rest at the agent's", () => {
      const { tokens } = tokenize("> hi\nok\n", opts);
      // "> hi" and its newline are the question; "ok" and its newline are not.
      expect(tokens.map((t) => t.delayMs)).toEqual([50, 50, 50, 50, 50, 10, 10, 10]);
    });

    it("sees the marker through the colour codes in front of it", () => {
      const { tokens } = tokenize(`${CYAN}> h${RESET}\n`, opts);
      expect(tokens.map((t) => t.delayMs)).toEqual([0, 50, 50, 50, 0, 50]);
    });

    it("does not let a CRLF end the question one character early", () => {
      const { tokens } = tokenize("> hi\r\n", opts);
      expect(tokens.map((t) => t.delayMs)).toEqual([50, 50, 50, 50, 0, 50]);
    });

    it("keeps a `>` in the middle of a line at the agent's pace", () => {
      // A comparison in a reply is not somebody typing.
      const { tokens } = tokenize("a > b\n", opts);
      expect(tokens.every((t) => t.delayMs === 10)).toBe(true);
    });

    it("carries an unfinished question across a chunk boundary", () => {
      const first = tokenize("> what is", opts);
      expect(first.state.inPrompt).toBe(true);
      const second = tokenize(" this?\nreply", { ...opts, ...first.state });
      expect(second.tokens[0].delayMs).toBe(50);
      // The newline closes the question; the reply that follows is the agent.
      expect(second.tokens[second.tokens.length - 1].delayMs).toBe(10);
      expect(second.state.inPrompt).toBe(false);
    });
  });

  describe("diverted to the prompt box", () => {
    it("routes the question to the box and closes it with a submit", () => {
      const { tokens } = tokenize("> hi\nok\n", split);
      expect(tokens.map((t) => [t.channel, t.text])).toEqual([
        ["prompt", ">"],
        ["prompt", " "],
        ["prompt", "h"],
        ["prompt", "i"],
        ["submit", "> hi\n"],
        ["agent", "o"],
        ["agent", "k"],
        ["agent", "\n"],
      ]);
    });

    it("charges the submit its own pause", () => {
      const { tokens } = tokenize("> hi\n", split);
      expect(tokens[tokens.length - 1]).toMatchObject({ channel: "submit", delayMs: 500 });
    });

    it("keeps the colour codes out of the box and in the echo", () => {
      const { tokens } = tokenize(`${CYAN}> h${RESET}\n`, split);
      // The box renders text, so no escape sequence is ever handed to it...
      expect(tokens.filter((t) => t.channel === "prompt").map((t) => t.text)).toEqual([
        ">",
        " ",
        "h",
      ]);
      // ...but the terminal echo is the recorded line, colours intact.
      const submit = tokens.find((t) => t.channel === "submit");
      expect(submit?.text).toBe(`${CYAN}> h${RESET}\n`);
    });

    it("folds the CRLF into the echo rather than the box", () => {
      const { tokens } = tokenize("> hi\r\n", split);
      expect(tokens.find((t) => t.channel === "submit")?.text).toBe("> hi\r\n");
      expect(tokens.some((t) => t.channel === "prompt" && t.text === "\r")).toBe(false);
    });

    it("holds a half-typed question in state until its line ends", () => {
      const first = tokenize("> what is", split);
      expect(first.state.promptRaw).toBe("> what is");
      expect(first.tokens.every((t) => t.channel === "prompt")).toBe(true);

      const second = tokenize(" it?\nreply\n", { ...split, ...first.state });
      expect(second.tokens.find((t) => t.channel === "submit")?.text).toBe("> what is it?\n");
      expect(second.state.promptRaw).toBe("");
    });
  });
});

describe("createPacedWriter (#2083)", () => {
  it("reveals nothing until time passes, then a character at a time", () => {
    const h = harness();
    h.writer.push("abcd");

    expect(h.text()).toBe("");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR);
    expect(h.text()).toBe("a");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 2);
    expect(h.text()).toBe("abc");
  });

  it("finishes a whole transcript given enough time", () => {
    const h = harness();
    const line = `${CYAN}> What is SciStudio?${RESET}\n`;
    h.writer.push(line);

    // A question line, so every visible character of it is at the reader's
    // pace; the escape sequences are free, which only makes this a ceiling.
    h.advance(line.length * SCRIPTED_PROMPT_MS_PER_CHAR + SCRIPTED_PARAGRAPH_PAUSE_MS);
    expect(h.text()).toBe(line);
    expect(h.writer.isTyping()).toBe(false);
    expect(h.hasPendingTimer()).toBe(false);
  });

  it("never splits a colour change across two writes", () => {
    const h = harness();
    h.writer.push(`${CYAN}ab${RESET}`);
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 10);

    // Whatever the chunking was, no write may contain a lone ESC with no final
    // byte after it — that is the state that leaves xterm's parser mid-sequence.
    for (const chunk of h.written) {
      const at = chunk.indexOf(ESC);
      if (at === -1) continue;
      expect(escapeSequenceEnd(chunk, at)).not.toBe(-1);
    }
    expect(h.text()).toBe(`${CYAN}ab${RESET}`);
  });

  it("holds the paragraph pause before the next line starts", () => {
    const h = harness();
    h.writer.push("a\n\nb");

    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 3);
    expect(h.text()).toBe("a\n");
    // The blank line's newline costs the pause on top of its own character.
    h.advance(SCRIPTED_PARAGRAPH_PAUSE_MS - SCRIPTED_AGENT_MS_PER_CHAR);
    expect(h.text()).toBe("a\n");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 2);
    expect(h.text()).toBe("a\n\nb");
  });

  it("finishNow releases the rest at once, carry included", () => {
    const h = harness();
    h.writer.push(`ab${ESC}[1`);
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR);
    expect(h.text()).toBe("a");

    h.writer.finishNow();
    expect(h.text()).toBe(`ab${ESC}[1`);
    expect(h.writer.isTyping()).toBe(false);
    expect(h.hasPendingTimer()).toBe(false);
  });

  it("is idempotent once everything has been released", () => {
    const h = harness();
    h.writer.push("ab");
    h.writer.finishNow();
    h.writer.finishNow();
    expect(h.text()).toBe("ab");
  });

  it("appends a later segment to the same queue", () => {
    const h = harness();
    h.writer.push("ab");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR);
    h.writer.push("cd");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 3);
    expect(h.text()).toBe("abcd");
  });

  it("forgives arrears beyond the catch-up cap rather than dumping the backlog", () => {
    const h = harness();
    const payload = "x".repeat(200);
    h.writer.push(payload);

    // A backgrounded tab: one timer fires after a very long sleep.
    h.jumpAndFire(10_000);

    const revealed = h.text().length;
    expect(revealed).toBeLessThanOrEqual(MAX_CATCHUP_MS / SCRIPTED_AGENT_MS_PER_CHAR + 1);
    expect(h.writer.isTyping()).toBe(true);
  });

  it("writes straight through when motion is reduced", () => {
    const h = harness({ instant: true });
    h.writer.push("abcd");
    expect(h.text()).toBe("abcd");
    expect(h.hasPendingTimer()).toBe(false);
  });

  it("stops writing once disposed", () => {
    const write = vi.fn();
    let clock = 0;
    // Boxed rather than a bare `let`: TypeScript cannot see that the callbacks
    // below run, so a plain variable narrows to `null` at the call site.
    const slot: { fn: (() => void) | null } = { fn: null };
    const writer = createPacedWriter({
      write,
      now: () => clock,
      setTimer: (fn) => {
        slot.fn = fn;
        return 1;
      },
      clearTimer: () => {
        slot.fn = null;
      },
    });

    writer.push("abcd");
    writer.dispose();
    clock += 1000;
    slot.fn?.();

    expect(write).not.toHaveBeenCalled();
    expect(writer.isTyping()).toBe(false);
  });
});

describe("createPacedWriter with a prompt box (#2083)", () => {
  const QUESTION = "> What is SciStudio?\n";
  const REPLY = "A workflow runtime.\n";

  it("types the question into the box, not into the terminal", () => {
    const h = harness({ box: true });
    h.writer.push(QUESTION + REPLY);

    h.advance(SCRIPTED_PROMPT_MS_PER_CHAR * 3);
    expect(h.box()).toBe("> W");
    // Nothing has reached the terminal yet: the question is still being typed.
    expect(h.text()).toBe("");
  });

  it("clears the box on Enter and echoes the question into the terminal", () => {
    const h = harness({ box: true });
    h.writer.push(QUESTION + REPLY);

    // Long enough to type the question but not to spend the submit pause.
    h.advance(QUESTION.length * SCRIPTED_PROMPT_MS_PER_CHAR);
    expect(h.box()).toBe("> What is SciStudio?");
    expect(h.text()).toBe("");

    // Past the Enter. The reply starts arriving immediately after, so this
    // asserts what the send did rather than trying to stop the clock on it.
    h.advance(SCRIPTED_SUBMIT_PAUSE_MS);
    expect(h.submits).toEqual(["> What is SciStudio?"]);
    expect(h.box()).toBe("");
    expect(h.text().startsWith(QUESTION)).toBe(true);
  });

  it("puts the reply in the terminal after the question is sent", () => {
    const h = harness({ box: true });
    h.writer.push(QUESTION + REPLY);

    h.advance(
      QUESTION.length * SCRIPTED_PROMPT_MS_PER_CHAR +
        SCRIPTED_SUBMIT_PAUSE_MS +
        REPLY.length * SCRIPTED_AGENT_MS_PER_CHAR +
        SCRIPTED_PARAGRAPH_PAUSE_MS,
    );
    expect(h.text()).toBe(QUESTION + REPLY);
    expect(h.box()).toBe("");
  });

  it("never shows the question in both places at once", () => {
    const h = harness({ box: true });
    h.writer.push(QUESTION + REPLY);
    // Step through the whole exchange and check the invariant at every tick.
    for (let i = 0; i < 200; i += 1) {
      h.advance(20);
      if (h.box() !== "" && h.text() !== "") {
        expect(h.text()).not.toContain(h.box());
      }
    }
  });

  it("finishNow sends a question in flight instead of dumping it into the terminal", () => {
    const h = harness({ box: true });
    h.writer.push(QUESTION + REPLY);
    h.advance(SCRIPTED_PROMPT_MS_PER_CHAR * 3);
    expect(h.box()).toBe("> W");

    h.writer.finishNow();
    expect(h.box()).toBe("");
    expect(h.submits).toEqual(["> What is SciStudio?"]);
    expect(h.text()).toBe(QUESTION + REPLY);
  });

  it("leaves a question with no Enter yet sitting in the box", () => {
    const h = harness({ box: true });
    h.writer.push("> half a quest");
    h.writer.finishNow();

    expect(h.box()).toBe("> half a quest");
    expect(h.submits).toEqual([]);
    expect(h.text()).toBe("");
  });

  it("still types into the terminal when the surface has no box", () => {
    const h = harness();
    h.writer.push(QUESTION);
    h.advance(QUESTION.length * SCRIPTED_PROMPT_MS_PER_CHAR + SCRIPTED_PARAGRAPH_PAUSE_MS);
    expect(h.text()).toBe(QUESTION);
    expect(h.box()).toBe("");
  });
});

describe("reporting that the reply has finished (#2083)", () => {
  /** A writer whose idle reports the test can count. */
  function idleHarness(options: { instant?: boolean } = {}) {
    let clock = 0;
    let pending: { fn: () => void; dueAt: number } | null = null;
    const idles: number[] = [];
    const written: string[] = [];

    const writer = createPacedWriter({
      write: (data) => written.push(data),
      instant: options.instant ?? false,
      onIdle: () => idles.push(clock),
      now: () => clock,
      setTimer: (fn, ms) => {
        pending = { fn, dueAt: clock + ms };
        return 1;
      },
      clearTimer: () => {
        pending = null;
      },
    });

    const advance = (ms: number): void => {
      const target = clock + ms;
      for (let guard = 0; guard < 10_000; guard += 1) {
        if (pending === null || pending.dueAt > target) break;
        clock = Math.max(clock, pending.dueAt);
        const due = pending;
        pending = null;
        due.fn();
      }
      clock = target;
    };

    return { writer, idles, advance, text: () => written.join("") };
  }

  it("reports once, after the last character is on screen", () => {
    const h = idleHarness();
    h.writer.push("abcd");

    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 2);
    expect(h.idles).toHaveLength(0);

    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 10);
    expect(h.idles).toHaveLength(1);
    // The whole reply is written before the report: that is the entire point
    // of the signal.
    expect(h.text()).toBe("abcd");
  });

  it("does not report again while nothing new has arrived", () => {
    const h = idleHarness();
    h.writer.push("ab");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 10);
    expect(h.idles).toHaveLength(1);

    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 100);
    expect(h.idles).toHaveLength(1);
  });

  it("reports once per reply", () => {
    const h = idleHarness();
    h.writer.push("ab");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 10);
    h.writer.push("cd");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR * 10);
    expect(h.idles).toHaveLength(2);
  });

  it("reports when the reader skips to the end", () => {
    const h = idleHarness();
    h.writer.push("abcdefgh");
    h.advance(SCRIPTED_AGENT_MS_PER_CHAR);
    expect(h.idles).toHaveLength(0);

    h.writer.finishNow();
    // A reader who skipped has still reached the end, and what the reply said
    // is as true now as it would have been in ten seconds.
    expect(h.idles).toHaveLength(1);
    expect(h.text()).toBe("abcdefgh");

    // ...and finishing an already-empty queue does not report a second time.
    h.writer.finishNow();
    expect(h.idles).toHaveLength(1);
  });

  it("still reports under reduced motion", () => {
    const h = idleHarness({ instant: true });
    h.writer.push("abcd");
    // Nothing is ever queued on this path, so without an explicit report the
    // caller waiting on it would wait forever and the step could never finish.
    expect(h.idles).toHaveLength(1);
  });

  it("never reports for a writer nothing was pushed to", () => {
    const h = idleHarness();
    h.advance(10_000);
    expect(h.idles).toHaveLength(0);
  });
});
