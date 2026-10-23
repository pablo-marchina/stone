/** Incremental SSE parser: events are complete only at a blank-line boundary. */
export class SSEParser {
  constructor(onEvent) { this.buffer = ''; this.onEvent = onEvent; }
  feed(chunk) {
    this.buffer += chunk;
    // Handle CRLF and LF (including a CRLF split across network chunks).
    let match;
    while ((match = /\r?\n\r?\n/.exec(this.buffer)) !== null) {
      const frame = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const item = { id: null, event: 'message', data: [] };
      for (const line of frame.split(/\r?\n/)) {
        if (!line || line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const key = colon < 0 ? line : line.slice(0, colon);
        const val = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
        if (key === 'data') item.data.push(val);
        else if (key === 'id') item.id = val;
        else if (key === 'event') item.event = val;
      }
      if (item.data.length) this.onEvent({ id: item.id, event: item.event, data: item.data.join('\n') });
    }
  }
  reset() { this.buffer = ''; }
}
