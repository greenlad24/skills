// Thin Claude Messages API client for the extension's service worker.
// Runs in the background context (not the page), so the API key never touches
// meet.google.com's JS. Calls go direct to api.anthropic.com with the
// browser-access header Anthropic requires for extension/browser origins.

const API_URL = "https://api.anthropic.com/v1/messages";
const API_VERSION = "2023-06-01";

function headers(apiKey) {
  return {
    "content-type": "application/json",
    "x-api-key": apiKey,
    "anthropic-version": API_VERSION,
    // Required for requests originating from a browser / extension.
    "anthropic-dangerous-direct-browser-access": "true",
  };
}

// Some models reject an explicit thinking block; some benefit from disabling it
// for latency. Return the right thinking param (or undefined to omit).
function thinkingFor(model) {
  const m = (model || "").toLowerCase();
  if (m.includes("fable") || m.includes("mythos")) return undefined; // always on
  if (m.includes("opus-4-8") || m.includes("opus-4-7") || m.includes("sonnet-5"))
    return { type: "disabled" }; // snappy answers
  return undefined; // haiku / older sonnet: no thinking by default
}

function answerSystem(s) {
  const name = s.userName?.trim() || "the user";
  const lang =
    s.language && s.language !== "auto"
      ? `\nAlways respond in ${s.language}.`
      : "";
  const ctx = s.userContext?.trim()
    ? `\n\nWhat you know about ${name} (use it to answer accurately):\n${s.userContext.trim()}`
    : "";
  return (
    `You are a private, real-time meeting copilot for ${name} during a live video call. ` +
    `You see the running transcript. When ${name} is asked something, or there is a clear ` +
    `opening to add value, write the answer ${name} should say — first person, as if ${name} ` +
    `is speaking. Be specific and confident. 1–3 sentences, no preamble, no "you could say", ` +
    `no meta-commentary. If facts are needed that only ${name} would know and you don't have ` +
    `them, give 2–3 short talking-point bullets instead. Never reveal that an assistant is ` +
    `involved. Output plain text only.` +
    ctx +
    lang
  );
}

function gateSystem(s) {
  const name = s.userName?.trim() || "the user";
  return (
    `You are the trigger for a meeting copilot. Decide if it should surface a suggested ` +
    `answer for ${name} right now, based on the recent transcript and the latest line. ` +
    `Reply with exactly one word: RESPOND or SKIP. Choose RESPOND only if ${name} is being ` +
    `asked a question or could clearly and usefully add something. Prefer SKIP for small talk, ` +
    `scheduling/logistics, or lines not aimed at ${name}.`
  );
}

function userContent(s, transcript, question, speaker) {
  const name = s.userName?.trim() || "the user";
  const who = speaker ? ` (from ${speaker})` : "";
  return (
    `Recent transcript:\n${transcript || "(none yet)"}\n\n` +
    `Latest line${who}: "${question}"\n\n` +
    `Provide ${name}'s response now.`
  );
}

// Non-streaming gate. Returns true if the copilot should answer.
export async function runGate({ settings, transcript, question, speaker }) {
  const body = {
    model: settings.gateModel,
    max_tokens: 5,
    system: [
      { type: "text", text: gateSystem(settings), cache_control: { type: "ephemeral" } },
    ],
    messages: [
      { role: "user", content: userContent(settings, transcript, question, speaker) },
    ],
  };
  const res = await fetch(API_URL, {
    method: "POST",
    headers: headers(settings.apiKey),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errText(res));
  const data = await res.json();
  const text = (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("")
    .trim()
    .toUpperCase();
  return text.startsWith("RESPOND");
}

// Streaming answer. Calls onDelta(text) as tokens arrive; resolves with the
// full text. mode: "answer" (transcript-driven) or "ask" (free-form question).
export async function streamAnswer({
  settings,
  transcript,
  question,
  speaker,
  mode,
  onDelta,
  signal,
}) {
  const thinking = thinkingFor(settings.answerModel);
  const body = {
    model: settings.answerModel,
    max_tokens: mode === "ask" ? 400 : 180,
    stream: true,
    system: [
      { type: "text", text: answerSystem(settings), cache_control: { type: "ephemeral" } },
    ],
    messages: [
      {
        role: "user",
        content:
          mode === "ask"
            ? `Recent transcript:\n${transcript || "(none yet)"}\n\nQuestion from ${
                settings.userName || "the user"
              }: ${question}`
            : userContent(settings, transcript, question, speaker),
      },
    ],
  };
  if (thinking) body.thinking = thinking;

  const res = await fetch(API_URL, {
    method: "POST",
    headers: headers(settings.apiKey),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(await errText(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const l = line.trim();
      if (!l.startsWith("data:")) continue;
      const payload = l.slice(5).trim();
      if (payload === "[DONE]") continue;
      let evt;
      try {
        evt = JSON.parse(payload);
      } catch {
        continue;
      }
      if (
        evt.type === "content_block_delta" &&
        evt.delta &&
        evt.delta.type === "text_delta"
      ) {
        full += evt.delta.text;
        onDelta && onDelta(evt.delta.text);
      } else if (evt.type === "error") {
        throw new Error(evt.error?.message || "stream error");
      }
    }
  }
  return full;
}

async function errText(res) {
  let detail = "";
  try {
    const j = await res.json();
    detail = j.error?.message || JSON.stringify(j.error || j);
  } catch {
    detail = await res.text().catch(() => "");
  }
  if (res.status === 401) return "Invalid API key (401). Check it in settings.";
  if (res.status === 429) return "Rate limited (429). Slow down or check your plan.";
  return `Claude API error ${res.status}: ${detail}`.slice(0, 300);
}

export function modelLabel(model) {
  const map = {
    "claude-fable-5": "Fable 5",
    "claude-opus-4-8": "Opus 4.8",
    "claude-sonnet-5": "Sonnet 5",
    "claude-haiku-4-5": "Haiku 4.5",
  };
  return map[model] || model;
}
