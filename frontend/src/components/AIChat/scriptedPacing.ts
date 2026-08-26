/**
 * ADR-053 FR-061a (#2083) — a scripted reply arrives at a speaking pace.
 *
 * The replay tab plays a pre-recorded agent transcript. Fed straight into
 * xterm, a whole segment lands in one frame: the question, the tool call and
 * the answer all appear together, already finished. That reads as a document
 * being pasted, not as a conversation happening — and this level's entire
 * subject is watching an agent work. So the bytes are released a character at
 * a time, the same device (and the same cadence) the tutorial's own dialogue
 * box uses for Mio's lines.
 *
 * Three rules, each load-bearing:
 *
 * **An escape sequence is one token and costs no time.** Splitting `\x1b[36m`
 * across two writes would leave xterm's parser holding half a sequence for a
 * frame, and paying 16ms per byte for bytes nobody can see would stall the
 * line for a fifth of a second on a colour change. Colour is applied whole and
 * instantly; only what the reader can read is paced.
 *
 * **A blank line costs extra.** The transcripts are structured — banner, then
 * the question, then the tool calls, then the prose — and the boundary between
 * those parts is a blank line. Pausing there is what turns a uniform stream
 * into an exchange with beats in it.
 *
 * **Catching up is capped.** A backgrounded tab's timers are throttled to once
 * a second or worse. Without a cap, coming back would dump the whole backlog
 * in one frame, which is exactly the behaviour this module exists to remove.
 * At most {@link MAX_CATCHUP_MS} of arrears is honoured; the rest is forgiven.
 *
 * `prefers-reduced-motion` turns the whole thing off, which is also what the
 * test environment reports (`vitest.setup.ts` answers "reduce") — so every
 * existing assertion about terminal output still reads a finished transcript.
 */

/**
 * Milliseconds per visible character of the agent's own output — its replies
 * and the tool calls it narrates.
 *
 * Faster than a person could type, because that is what an agent is: the reply
 * arrives at machine speed. Slow enough that the arrival is still legible as
 * arrival rather than as a paste.
 */
export const SCRIPTED_AGENT_MS_PER_CHAR = 8;

/**
 * Milliseconds per visible character of the reader's own question.
 *
 * A question is typed by a human, so it comes in at a human's pace — and the
 * contrast is the point: the same terminal visibly runs at two speeds, and the
 * slow half is the half a person wrote. A one-line question lands in about two
 * seconds, which is long enough to read as typing and short enough that nobody
 * waits on it.
 */
export const SCRIPTED_PROMPT_MS_PER_CHAR = 45;

/**
 * The marker that opens a line the reader is "typing".
 *
 * The transcripts print every question as a line whose first visible character
 * is `>`, the shell convention they already follow, so nothing needed adding to
 * the assets for the pacer to tell the two voices apart. It is a real contract
 * rather than a guess: `test_core_tutorials.py` holds every shipped transcript
 * to it, so a reply line that happens to open with a quote marker fails the
 * suite instead of silently typing itself out at a human's pace.
 */
export const PROMPT_LINE_MARKER = ">";

/**
 * Extra milliseconds spent on the newline that closes a blank line.
 *
 * Long enough to register as "that part is finished", short enough that a
 * transcript with five paragraph breaks does not spend two seconds on nothing.
 */
export const SCRIPTED_PARAGRAPH_PAUSE_MS = 400;

/**
 * How long the finished question sits in the input box before it is sent.
 *
 * The beat between typing the last character and pressing Enter. Without it the
 * question is gone the instant it is complete and the box never holds anything
 * long enough to read.
 */
export const SCRIPTED_SUBMIT_PAUSE_MS = 550;

/** The most arrears a throttled or backgrounded tab may spend at once. */
export const MAX_CATCHUP_MS = 120;

/**
 * Where a token goes.
 *
 * - `agent`: the transcript's own output, written to the terminal.
 * - `prompt`: one visible character of the reader's question, typed into the
 *   input box below the terminal.
 * - `submit`: the question is finished and sent. The box is cleared and the
 *   whole question line — colour codes and all — lands in the terminal's
 *   scrollback, the way a real agent CLI echoes what you just sent.
 */
export type TokenChannel = "agent" | "prompt" | "submit";

/** One indivisible piece of the stream, and what it costs to reveal. */
interface Token {
  text: string;
  delayMs: number;
  channel: TokenChannel;
}

/**
 * The input box below the terminal, when the surface has one.
 *
 * Its absence is meaningful rather than a default: a writer with no box types
 * the question into the terminal itself, which is what a bare paced terminal
 * did before the agent window existed.
 */
export interface PromptSink {
  /** Append one typed character to the box. */
  onType: (text: string) => void;
  /** The box was sent: clear it. Called before the line reaches the terminal. */
  onSubmit: () => void;
}

export interface PacedWriter {
  /** Queue more scripted bytes. Safe to call while the queue is draining. */
  push(data: string): void;
  /** Release everything queued right now. Idempotent. */
  finishNow(): void;
  /** Whether anything is still waiting to be revealed. */
  isTyping(): boolean;
  /** Stop the timer and drop the queue. The sink is not called again. */
  dispose(): void;
}

export interface PacedWriterOptions {
  /** Where revealed text goes — in the product, xterm's `write`. */
  write: (data: string) => void;
  /** Reveal everything the moment it is pushed (reduced motion, tests). */
  instant?: boolean;
  /** Milliseconds per character of the agent's own output. */
  agentMsPerChar?: number;
  /** Milliseconds per character of a line the reader is "typing". */
  promptMsPerChar?: number;
  paragraphPauseMs?: number;
  submitPauseMs?: number;
  /** The input box the question is typed into, when the surface has one. */
  promptSink?: PromptSink;
  /**
   * Called once each time the queue empties after having had something in it.
   *
   * "The reply has finished arriving" — the signal the tutorial runtime waits
   * on before landing what the reply claimed (#2083). Fired on `finishNow` too,
   * because a reader who skipped to the end has still reached the end.
   */
  onIdle?: () => void;
  /** Injectable clock and timer, so the pacing itself is testable. */
  now?: () => number;
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (handle: number) => void;
}

/**
 * Where the escape sequence starting at `start` ends, or -1 if `data` runs out
 * before it is terminated.
 *
 * Handles the two forms the transcripts and any real agent CLI produce: CSI
 * (`\x1b[` … final byte in `@`–`~`, which covers every SGR colour change) and
 * OSC (`\x1b]` … BEL or ST). Anything else escape-prefixed is the two-byte
 * form, which is what `\x1bM` and friends are.
 */
export function escapeSequenceEnd(data: string, start: number): number {
  if (data[start] !== "\x1b") return start + 1;
  const kind = data[start + 1];
  if (kind === undefined) return -1;

  if (kind === "[") {
    for (let i = start + 2; i < data.length; i += 1) {
      const code = data.charCodeAt(i);
      if (code >= 0x40 && code <= 0x7e) return i + 1;
    }
    return -1;
  }

  if (kind === "]") {
    for (let i = start + 2; i < data.length; i += 1) {
      if (data[i] === "\x07") return i + 1;
      if (data[i] === "\x1b" && data[i + 1] === "\\") return i + 2;
    }
    return -1;
  }

  return start + 2;
}

/** How far into the stream the tokenizer is, carried between chunks. */
export interface TokenizeState {
  /** The last visible character emitted, or "" at the start of the stream. */
  lastVisible: string;
  /** Whether the line being tokenized is the reader's question. */
  inPrompt: boolean;
  /**
   * The question line exactly as recorded, colour codes included, accumulated
   * while it is being typed so the `submit` token can echo it into the
   * terminal the moment the box is sent.
   */
  promptRaw: string;
  /**
   * Escape sequences seen at the start of a line, before its first visible
   * character has said whose line it is.
   *
   * They cannot be emitted on sight. The transcripts open the question with
   * `\x1b[1m\x1b[36m` and only then write `>`, so a sequence released
   * immediately would colour the terminal for a line that is about to be
   * diverted into the box — and the echo would arrive later missing the colour
   * it was recorded with.
   */
  pendingEscapes: string;
}

export interface TokenizeOptions extends TokenizeState {
  agentMsPerChar: number;
  promptMsPerChar: number;
  paragraphPauseMs: number;
  submitPauseMs: number;
  /**
   * Whether the question goes to an input box of its own.
   *
   * False on a bare paced terminal, where there is nowhere else for it to go
   * and it is typed into the terminal like everything else.
   */
  splitPrompt: boolean;
}

/** The starting state for a fresh stream. */
export const INITIAL_TOKENIZE_STATE: TokenizeState = {
  lastVisible: "",
  inPrompt: false,
  promptRaw: "",
  pendingEscapes: "",
};

/**
 * Split `data` into paced tokens.
 *
 * Returns the tokens, the state to carry into the next chunk, and whatever
 * trailing bytes could not be classified yet — an escape sequence cut in half
 * by a chunk boundary. The caller carries that remainder rather than emitting
 * it, because a partial sequence is neither a character to pace nor a colour to
 * apply.
 *
 * The state exists so that a chunk boundary is invisible to the pacing: a blank
 * line and a question line both survive being split across two pushes.
 */
export function tokenize(
  data: string,
  {
    agentMsPerChar,
    promptMsPerChar,
    paragraphPauseMs,
    submitPauseMs,
    splitPrompt,
    lastVisible,
    inPrompt,
    promptRaw,
    pendingEscapes,
  }: TokenizeOptions,
): { tokens: Token[]; carry: string; state: TokenizeState } {
  const tokens: Token[] = [];
  let previous = lastVisible;
  let prompt = inPrompt;
  let raw = promptRaw;
  let held = pendingEscapes;
  let i = 0;

  /* True before the first visible character of a line has been emitted. */
  const atLineStart = (): boolean => previous === "" || previous === "\n";
  /* Whether the question is being typed somewhere other than the terminal. */
  const diverted = (): boolean => prompt && splitPrompt;
  const state = (): TokenizeState => ({
    lastVisible: previous,
    inPrompt: prompt,
    promptRaw: raw,
    pendingEscapes: held,
  });

  /**
   * Let go of the line's opening escape sequences, now that its first visible
   * character has said where the line is going.
   */
  const releaseHeld = (toRaw: boolean): void => {
    if (!held) return;
    if (toRaw) raw += held;
    else tokens.push({ text: held, delayMs: 0, channel: "agent" });
    held = "";
  };

  while (i < data.length) {
    const ch = data[i];

    if (ch === "\x1b") {
      const end = escapeSequenceEnd(data, i);
      if (end === -1) return { tokens, carry: data.slice(i), state: state() };
      const sequence = data.slice(i, end);
      // Colour is not a character, so it neither costs time nor opens a line:
      // the question's own `\x1b[36m` must not consume the line-start slot the
      // `>` after it needs.
      if (diverted()) {
        // Inside a diverted question it is held back for the echo, because the
        // input box renders text, not ANSI.
        raw += sequence;
      } else if (splitPrompt && atLineStart()) {
        // Whose line this is, is not known yet. See `pendingEscapes`.
        held += sequence;
      } else {
        tokens.push({ text: sequence, delayMs: 0, channel: "agent" });
      }
      i = end;
      continue;
    }

    if (ch === "\r") {
      // Carriage return moves the cursor; it reveals nothing, so it is free —
      // and the transcripts' CRLF line endings must not end the prompt line one
      // character early.
      if (diverted()) raw += ch;
      else tokens.push({ text: ch, delayMs: 0, channel: "agent" });
      i += 1;
      continue;
    }

    if (ch === "\n") {
      if (diverted()) {
        // The question is finished. Pressing Enter is its own beat, and the
        // token carries the recorded line so the terminal can echo it.
        raw += ch;
        tokens.push({ text: raw, delayMs: submitPauseMs, channel: "submit" });
        raw = "";
      } else {
        // An empty line held nothing to decide whose it was; it is the agent's.
        releaseHeld(false);
        // A newline whose predecessor was also a newline closes a blank line —
        // the transcripts' paragraph boundary.
        const blank = previous === "\n";
        const cost = prompt ? promptMsPerChar : agentMsPerChar;
        tokens.push({ text: ch, delayMs: cost + (blank ? paragraphPauseMs : 0), channel: "agent" });
      }
      previous = ch;
      // The question ends with its line. Whatever follows is the agent again.
      prompt = false;
      i += 1;
      continue;
    }

    // A line that opens with `>` is the reader typing; the rest of that line
    // goes at their pace.
    if (atLineStart() && ch === PROMPT_LINE_MARKER) prompt = true;

    if (diverted()) {
      // This is the character that decided the line: the escapes in front of it
      // belong to the question and travel with it into the echo.
      releaseHeld(true);
      raw += ch;
      tokens.push({ text: ch, delayMs: promptMsPerChar, channel: "prompt" });
    } else {
      releaseHeld(false);
      tokens.push({
        text: ch,
        delayMs: prompt ? promptMsPerChar : agentMsPerChar,
        channel: "agent",
      });
    }
    previous = ch;
    i += 1;
  }

  return { tokens, carry: "", state: state() };
}

/**
 * Build a writer that reveals pushed text at a speaking pace.
 *
 * The writer owns one timer at a time and coalesces every token it releases in
 * a tick into a single call to `write`: xterm is happiest with a few larger
 * writes, and the pacing lives in *when* the tick happens rather than in how
 * many calls it makes.
 */
export function createPacedWriter(options: PacedWriterOptions): PacedWriter {
  const {
    write,
    instant = false,
    agentMsPerChar = SCRIPTED_AGENT_MS_PER_CHAR,
    promptMsPerChar = SCRIPTED_PROMPT_MS_PER_CHAR,
    paragraphPauseMs = SCRIPTED_PARAGRAPH_PAUSE_MS,
    submitPauseMs = SCRIPTED_SUBMIT_PAUSE_MS,
    promptSink,
    onIdle,
    now = () => (typeof performance !== "undefined" ? performance.now() : Date.now()),
    setTimer = (fn, ms) => window.setTimeout(fn, ms),
    clearTimer = (handle) => window.clearTimeout(handle),
  } = options;

  const splitPrompt = promptSink !== undefined;
  const queue: Token[] = [];
  let carry = "";
  let state: TokenizeState = { ...INITIAL_TOKENIZE_STATE };
  let timer: number | null = null;
  /**
   * When the token at the head of the queue is due, on the same clock as
   * `now()`. Meaningless while the queue is empty.
   *
   * A schedule rather than a spend-down budget, and the difference matters: a
   * budget capped at {@link MAX_CATCHUP_MS} can never afford a token that costs
   * more than the cap, so the blank-line pause would stall the stream forever.
   * A due time is capped in the only place the cap is actually about — how far
   * behind the schedule a throttled tab is allowed to be.
   */
  let dueAt = 0;
  let disposed = false;
  /*
   * Whether anything has been queued since the last idle report. Without it,
   * a writer that never receives a byte would still report going quiet, and a
   * second `finishNow` on an already-empty queue would report again.
   */
  let busy = false;

  /** Report the queue running dry, at most once per thing that filled it. */
  const reportIdle = (): void => {
    if (!busy) return;
    busy = false;
    onIdle?.();
  };

  const stopTimer = (): void => {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
  };

  /**
   * Release one token to wherever it belongs, buffering terminal writes.
   *
   * Terminal text is accumulated by the caller and written once per tick —
   * xterm prefers a few larger writes — but a `submit` has to interrupt that
   * buffer: the box must be cleared before its echo reaches the terminal, or
   * the reader sees the question in both places at once.
   */
  const release = (token: Token, buffered: string): string => {
    if (token.channel === "prompt") {
      promptSink?.onType(token.text);
      return buffered;
    }
    if (token.channel === "submit") {
      if (buffered) write(buffered);
      promptSink?.onSubmit();
      write(token.text);
      return "";
    }
    return buffered + token.text;
  };

  const drain = (): void => {
    if (disposed) return;
    timer = null;
    if (queue.length === 0) return;

    const current = now();
    // Forgive arrears past the cap: a tab that was backgrounded for ten seconds
    // resumes from a schedule that is only just behind, instead of paying out
    // ten seconds of backlog in this one frame.
    if (current - dueAt > MAX_CATCHUP_MS) dueAt = current - MAX_CATCHUP_MS;

    let out = "";
    while (queue.length > 0 && dueAt <= current) {
      out = release(queue.shift() as Token, out);
      if (queue.length > 0) dueAt += queue[0].delayMs;
    }
    if (out) write(out);

    if (queue.length > 0) {
      // Wake when the head token comes due. The 50ms ceiling keeps a long
      // paragraph pause from becoming one unresponsive sleep, so a finishNow()
      // during it is still felt promptly.
      timer = setTimer(drain, Math.min(Math.max(dueAt - current, 0), 50));
      return;
    }
    // Reported after the last write, never before it: the whole point of the
    // signal is that everything the reply said is already on screen.
    reportIdle();
  };

  const start = (): void => {
    if (timer !== null || queue.length === 0) return;
    dueAt = now() + queue[0].delayMs;
    timer = setTimer(drain, Math.min(queue[0].delayMs, 50));
  };

  return {
    push(data: string): void {
      if (disposed || !data) return;
      if (instant) {
        write(data);
        // Still reported, and it has to be: the reply is finished the instant
        // it is written, and a caller waiting on this signal to land what the
        // reply promised would otherwise wait forever under reduced motion.
        busy = true;
        reportIdle();
        return;
      }
      const result = tokenize(carry + data, {
        agentMsPerChar,
        promptMsPerChar,
        paragraphPauseMs,
        submitPauseMs,
        splitPrompt,
        ...state,
      });
      carry = result.carry;
      state = result.state;
      if (result.tokens.length > 0 || result.carry) busy = true;
      queue.push(...result.tokens);
      start();
    },

    finishNow(): void {
      if (disposed) return;
      stopTimer();
      let out = "";
      // Released through the same path, so a question still in flight lands in
      // the box, its Enter still clears the box before the echo, and nothing
      // typed into the box is also dumped into the terminal.
      while (queue.length > 0) out = release(queue.shift() as Token, out);
      // A half-read escape sequence is released too, and so are the ones held
      // back waiting to learn whose line they open: keeping either would leave
      // the transcript short of a colour change it was recorded with.
      if (state.pendingEscapes) {
        out += state.pendingEscapes;
        state = { ...state, pendingEscapes: "" };
      }
      if (carry) {
        out += carry;
        carry = "";
      }
      if (out) write(out);
      // A reader who skipped to the end has still reached the end, and the
      // reply's claims are as true now as they would have been in ten seconds.
      reportIdle();
    },

    isTyping(): boolean {
      return !disposed && queue.length > 0;
    },

    dispose(): void {
      disposed = true;
      stopTimer();
      queue.length = 0;
      carry = "";
    },
  };
}
