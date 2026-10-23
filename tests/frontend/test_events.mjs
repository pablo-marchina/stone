import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SSEParser} from '../../src/tapi_gate0/web/events.mjs';

test('parses split SSE message exactly once', () => {
  const received=[];const p=new SSEParser(evt=>received.push(evt));
  p.feed('id: 7\nevent: domain_event\ndata: {"seq":7}');
  assert.equal(received.length,0);
  p.feed('\n\n');
  assert.deepEqual(received,[{id:'7',event:'domain_event',data:'{"seq":7}'}]);
});
test('ignores heartbeats and accepts CRLF', () => {
  const arr=[];const p=new SSEParser(x=>arr.push(x));
  p.feed(': keepalive\r\n\r\nid: 8\r\nevent: domain_event\r\ndata: ok\r\n\r\n');
  assert.equal(arr.length,1);assert.equal(arr[0].id,'8');
});
test('reset discards incomplete buffered event', () => {
  const arr=[];const p=new SSEParser(x=>arr.push(x));
  p.feed('data: incomplete');p.reset();p.feed('data: complete\n\n');
  assert.equal(arr[0].data,'complete');
});
