import { api } from "./api";
import type { AgentReply, TurnEvent } from "./types";

interface TurnHandlers {
  /** A step, an approval request, a block or an error, in the order they happen. */
  onEvent: (event: TurnEvent) => void;
  onReply: (reply: AgentReply) => void;
  onDone: () => void;
  /** The connection to the backend broke before the turn finished. */
  onLost: () => void;
}

const EVENT_NAMES = ["step", "approval_required", "blocked", "error"] as const;

/**
 * Follows one chat turn over Server-Sent Events. Returns a function that stops listening.
 * The backend replays a stream from its start, so the connection is never reopened here.
 */
export function followTurn(streamId: string, handlers: TurnHandlers): () => void {
  const source = new EventSource(api.chatStreamUrl(streamId));
  let finished = false;

  function close() {
    finished = true;
    source.close();
  }

  for (const name of EVENT_NAMES) {
    source.addEventListener(name, (event) => {
      // The browser also reports a broken connection as an "error" event, with no data.
      if (!(event instanceof MessageEvent)) {
        if (!finished) {
          close();
          handlers.onLost();
        }
        return;
      }
      handlers.onEvent({ event: name, data: JSON.parse(event.data) } as TurnEvent);
    });
  }
  source.addEventListener("message", (event) => handlers.onReply(JSON.parse(event.data) as AgentReply));
  source.addEventListener("done", () => {
    close();
    handlers.onDone();
  });
  return close;
}
