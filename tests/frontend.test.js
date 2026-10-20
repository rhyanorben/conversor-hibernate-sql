import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApi } from '../hibernate_sql/presentation/web/api.js';
import { createController } from '../hibernate_sql/presentation/web/controller.js';

function element() {
  const classes = new Set();
  return {
    value: '', disabled: false, textContent: '', className: '', options: [],
    classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
    contains: () => false,
    focus() { this.focused = true; },
    select() { this.selected = true; },
    append(option) { this.options.push(option); this.value ||= option.value; },
  };
}

function setup(overrides = {}) {
  const elements = Object.fromEntries(
    ['logs', 'output', 'status', 'prefix', 'normal', 'command', 'clear', 'copy', 'file', 'dropZone', 'download']
      .map(id => [id, element()]),
  );
  const requests = [];
  const api = {
    prefixes: async () => ['EXPLAIN ANALYZE'],
    convert: async (...args) => {
      requests.push(args);
      return { sql: 'select 1\n;', count: 1 };
    },
    ...overrides,
  };
  const copied = [];
  const clipboard = { writeText: async text => copied.push(text) };
  const downloads = [];
  const controller = createController(elements, api, clipboard, label => ({ value: label, textContent: label }), sql => downloads.push(sql));
  return { elements, controller, requests, copied, downloads };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((accept, decline) => { resolve = accept; reject = decline; });
  return { promise, resolve, reject };
}

test('API sends JSON and retrieves prefixes', async () => {
  const calls = [];
  const api = createApi(async (...args) => {
    calls.push(args);
    return { ok: true, json: async () => ({ count: 1 }) };
  });
  assert.deepEqual(await api.convert('á', 'EXPLAIN'), { count: 1 });
  assert.deepEqual(calls[0], ['/convert', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ log: 'á', prefix: 'EXPLAIN' }),
  }]);
  await api.prefixes();
  assert.equal(calls[1][0], '/prefixes');
});

test('API reports server errors and has a fallback message', async () => {
  for (const payload of [{ error: 'Invalid log' }, {}]) {
    const api = createApi(async () => ({ ok: false, json: async () => payload }));
    await assert.rejects(api.prefixes(), { message: payload.error || 'Não foi possível concluir a requisição.' });
  }
});

test('API propagates network and malformed JSON failures', async () => {
  const networkApi = createApi(async () => { throw new Error('offline'); });
  await assert.rejects(networkApi.prefixes(), /offline/);
  const malformedApi = createApi(async () => ({ ok: true, json: async () => { throw new Error('JSON'); } }));
  await assert.rejects(malformedApi.prefixes(), /JSON/);
});

test('initialization loads commands and wires every button', async () => {
  const { controller, elements, requests, copied } = setup();
  await controller.initialize();
  assert.deepEqual(elements.prefix.options, [{ value: 'EXPLAIN ANALYZE', textContent: 'EXPLAIN ANALYZE' }]);
  assert.equal(elements.command.disabled, false);
  assert.equal(elements.copy.disabled, true);
  elements.logs.value = 'Hibernate: select 1';
  await elements.normal.onclick();
  assert.deepEqual(requests[0], ['Hibernate: select 1', '']);
  assert.equal(elements.output.value, 'select 1\n;');
  assert.equal(elements.copy.disabled, false);
  assert.equal(elements.status.textContent, '1 query(s) montada(s).');
  await elements.command.onclick();
  assert.equal(requests[1][1], 'EXPLAIN ANALYZE');
  await elements.copy.onclick();
  assert.deepEqual(copied, ['select 1\n;']);
  assert.equal(elements.status.textContent, 'SQL copiada.');
  elements.clear.onclick();
  assert.equal(elements.logs.value, '');
  assert.equal(elements.output.value, '');
  assert.equal(elements.copy.disabled, true);
  assert.equal(elements.status.textContent, '');
  assert.equal(elements.logs.focused, true);
});

test('empty and failed command lists keep the command button disabled', async () => {
  const empty = setup({ prefixes: async () => [] });
  await empty.controller.initialize();
  assert.equal(empty.elements.command.disabled, true);
  const failure = setup({ prefixes: async () => { throw new Error('offline'); } });
  await failure.controller.initialize();
  assert.equal(failure.elements.command.disabled, true);
  assert.equal(failure.elements.status.className, 'error');
  assert.match(failure.elements.status.textContent, /carregar os comandos/);
});

test('conversion errors clear old output and unlock buttons', async () => {
  const { controller, elements } = setup({ convert: async () => { throw new Error('Invalid input'); } });
  await controller.initialize();
  elements.output.value = 'old';
  await controller.generate(false);
  assert.equal(elements.output.value, '');
  assert.equal(elements.copy.disabled, true);
  assert.equal(elements.normal.disabled, false);
  assert.equal(elements.command.disabled, false);
  assert.equal(elements.status.textContent, 'Invalid input');
  assert.equal(elements.status.className, 'error');
});

test('concurrent generation is prevented while a request is pending', async () => {
  const pending = deferred();
  let requests = 0;
  const { controller, elements } = setup({ convert: () => { requests++; return pending.promise; } });
  await controller.initialize();
  const running = controller.generate(false);
  assert.equal(elements.normal.disabled, true);
  assert.equal(elements.command.disabled, true);
  await controller.generate(true);
  assert.equal(requests, 1);
  pending.resolve({ sql: '', count: 0 });
  await running;
  assert.equal(elements.normal.disabled, false);
  assert.equal(elements.copy.disabled, true);
});

test('clearing prevents late success or failure from restoring stale state', async () => {
  for (const succeeds of [true, false]) {
    const pending = deferred();
    const { controller, elements } = setup({ convert: () => pending.promise });
    await controller.initialize();
    const running = controller.generate(false);
    controller.clear();
    if (succeeds) pending.resolve({ sql: 'stale', count: 1 });
    else pending.reject(new Error('stale failure'));
    await running;
    assert.equal(elements.output.value, '');
    assert.equal(elements.status.textContent, '');
    assert.equal(elements.copy.disabled, true);
    assert.equal(elements.normal.disabled, false);
  }
});

test('an older response cannot replace a new conversion after clearing', async () => {
  const first = deferred();
  const second = deferred();
  let request = 0;
  const { controller, elements } = setup({ convert: () => (++request === 1 ? first.promise : second.promise) });
  await controller.initialize();
  const older = controller.generate(false);
  controller.clear();
  const newer = controller.generate(false);
  first.resolve({ sql: 'old', count: 1 });
  await older;
  assert.equal(elements.normal.disabled, true);
  second.resolve({ sql: 'new', count: 1 });
  await newer;
  assert.equal(elements.output.value, 'new');
});

test('clipboard failure selects SQL for manual copying', async () => {
  const { controller, elements } = setup();
  const fallback = createController(elements, {}, undefined, () => {});
  elements.output.value = 'select 1';
  await fallback.copy();
  assert.equal(elements.output.focused, true);
  assert.equal(elements.output.selected, true);
  assert.match(elements.status.textContent, /Ctrl\+C/);
  assert.ok(controller);
});

test('browser entry point binds real document elements to the controller', async () => {
  const state = setup();
  const blobs = [];
  const revoked = [];
  const links = [];
  const previous = {
    document: globalThis.document,
    window: globalThis.window,
    navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
    createObjectURL: URL.createObjectURL,
    revokeObjectURL: URL.revokeObjectURL,
  };
  try {
    globalThis.document = {
      getElementById: id => state.elements[id],
      createElement: () => ({ click() { this.clicked = true; }, remove() { this.removed = true; } }),
      body: { append: link => links.push(link) },
    };
    URL.createObjectURL = blob => { blobs.push(blob); return 'blob:test'; };
    URL.revokeObjectURL = url => revoked.push(url);
    globalThis.window = { fetch: async () => ({ ok: true, json: async () => ['EXPLAIN'] }) };
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: {} } });
    await import('../hibernate_sql/presentation/web/app.js');
    assert.equal(state.elements.prefix.options[0].value, 'EXPLAIN');
    assert.equal(typeof state.elements.normal.onclick, 'function');
    state.elements.output.value = 'select 123;';
    state.elements.download.onclick();
    assert.equal(await blobs[0].text(), 'select 123;');
    assert.equal(blobs[0].type, 'text/plain;charset=utf-8');
    assert.equal(links[0].href, 'blob:test');
    assert.equal(links[0].download, 'queries.sql');
    assert.equal(links[0].clicked, true);
    assert.equal(links[0].removed, true);
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.deepEqual(revoked, ['blob:test']);
  } finally {
    URL.createObjectURL = previous.createObjectURL;
    URL.revokeObjectURL = previous.revokeObjectURL;
    if (previous.document === undefined) delete globalThis.document;
    else globalThis.document = previous.document;
    if (previous.window === undefined) delete globalThis.window;
    else globalThis.window = previous.window;
    if (previous.navigator) Object.defineProperty(globalThis, 'navigator', previous.navigator);
    else delete globalThis.navigator;
  }
});

test('pasting converts the updated input without an additional command; typing invalidates output', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  elements.logs.value = 'Hibernate: select 123';
  await elements.logs.oninput({ inputType: 'insertFromPaste' });
  assert.deepEqual(requests, [['Hibernate: select 123', '']]);
  assert.equal(elements.output.value, 'select 1\n;');
  assert.equal(elements.download.disabled, false);
  await elements.logs.oninput({ inputType: 'insertText' });
  assert.equal(requests.length, 1);
  assert.equal(elements.output.value, '');
  assert.equal(elements.download.disabled, true);
  elements.logs.value = '  ';
  await elements.logs.oninput({ inputType: 'insertFromPaste' });
  assert.equal(requests.length, 1);
});

test('a new paste supersedes an in-flight conversion', async () => {
  const first = deferred();
  let requests = 0;
  const { controller, elements } = setup({ convert: async () => ++requests === 1 ? first.promise : { sql: 'new', count: 1 } });
  await controller.initialize();
  const older = controller.generate(false);
  elements.logs.value = 'new logs';
  await elements.logs.oninput({ inputType: 'insertFromPaste' });
  first.resolve({ sql: 'old', count: 1 });
  await older;
  assert.equal(elements.output.value, 'new');
  assert.equal(elements.download.disabled, false);
});

test('paste events also trigger conversion when the browser reports a generic input event', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  elements.logs.onpaste();
  elements.logs.value = 'Hibernate: select 123';
  await elements.logs.oninput({ inputType: 'insertText' });
  assert.deepEqual(requests, [['Hibernate: select 123', '']]);
  await elements.logs.oninput({ inputType: 'insertText' });
  assert.equal(requests.length, 1);
});

test('file selection is captured before resetting the live file input', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  const files = [logFile()];
  elements.file.files = files;
  Object.defineProperty(elements.file, 'value', { set() { files.length = 0; } });
  await elements.file.onchange();
  assert.deepEqual(requests, [['Hibernate: select 123', '']]);
});

function logFile(text = 'Hibernate: select 123', overrides = {}) {
  return { name: 'example.log', size: text.length, text: async () => text, ...overrides };
}

test('file selection loads logs, converts automatically, and allows reselecting the same file', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  elements.file.files = [logFile()];
  elements.file.value = 'example.log';
  await elements.file.onchange();
  assert.equal(elements.logs.value, 'Hibernate: select 123');
  assert.equal(elements.file.value, '');
  assert.deepEqual(requests, [['Hibernate: select 123', '']]);
  await elements.file.onchange();
  assert.equal(requests.length, 2);
});

test('dragging a file highlights the panel and dropping imports it; text drops stay native', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  let prevented = 0;
  const event = { preventDefault: () => prevented++, dataTransfer: { types: ['Files'], files: [logFile()] } };
  elements.dropZone.ondragover(event);
  assert.equal(elements.dropZone.classList.contains('dragging'), true);
  assert.equal(event.dataTransfer.dropEffect, 'copy');
  await elements.dropZone.ondrop(event);
  assert.equal(elements.dropZone.classList.contains('dragging'), false);
  assert.equal(requests.length, 1);
  const text = { preventDefault: () => prevented++, dataTransfer: { types: ['text/plain'], files: [] } };
  elements.dropZone.ondragover(text);
  await elements.dropZone.ondrop(text);
  assert.equal(prevented, 2);
});

test('invalid file imports report errors without reading or converting files', async () => {
  for (const [files, error] of [
    [[logFile(), logFile()], /um arquivo/],
    [[logFile('', { name: 'data.exe' })], /\.log ou \.txt/],
    [[logFile('', { size: 5_000_001 })], /5 MB/],
  ]) {
    const { controller, elements, requests } = setup();
    await controller.initialize();
    for (const file of files) file.text = () => assert.fail('should not read invalid files');
    elements.file.files = files;
    await elements.file.onchange();
    assert.match(elements.status.textContent, error);
    assert.equal(elements.status.className, 'error');
    assert.equal(elements.normal.disabled, false);
    assert.equal(elements.download.disabled, true);
    assert.equal(requests.length, 0);
  }
});

test('file cancellation leaves the current output unchanged and read failures unlock controls', async () => {
  const { controller, elements, requests } = setup();
  await controller.initialize();
  await controller.generate(false);
  elements.file.files = [];
  await elements.file.onchange();
  assert.equal(elements.output.value, 'select 1\n;');
  elements.file.files = [logFile('', { text: async () => { throw new Error('read failed'); } })];
  await elements.file.onchange();
  assert.match(elements.status.textContent, /ler o arquivo/);
  assert.equal(elements.normal.disabled, false);
  assert.equal(elements.download.disabled, true);
  assert.equal(requests.length, 1);
});

test('clearing, editing, or importing another file invalidates a pending file read', async () => {
  for (const action of ['clear', 'edit', 'replace']) {
    const pending = deferred();
    const { controller, elements, requests } = setup();
    await controller.initialize();
    elements.file.files = [logFile('', { text: () => pending.promise })];
    const reading = elements.file.onchange();
    assert.equal(elements.normal.disabled, true);
    if (action === 'clear') controller.clear();
    if (action === 'edit') {
      elements.logs.value = 'manually edited';
      await elements.logs.oninput({ inputType: 'insertText' });
    }
    if (action === 'replace') {
      elements.file.files = [logFile('replacement')];
      await elements.file.onchange();
    }
    pending.resolve('stale file');
    await reading;
    assert.equal(elements.logs.value, { clear: '', edit: 'manually edited', replace: 'replacement' }[action]);
    assert.equal(requests.length, action === 'replace' ? 1 : 0);
    assert.equal(elements.normal.disabled, false);
  }
});

test('download uses only the current SQL and is disabled after clear or conversion failure', async () => {
  const { controller, elements, downloads } = setup();
  await controller.initialize();
  elements.download.onclick();
  assert.deepEqual(downloads, []);
  await controller.generate(false);
  elements.download.onclick();
  assert.deepEqual(downloads, ['select 1\n;']);
  controller.clear();
  assert.equal(elements.download.disabled, true);
  elements.download.onclick();
  assert.equal(downloads.length, 1);
  const failure = setup({ convert: async () => { throw new Error('invalid'); } });
  await failure.controller.initialize();
  await failure.controller.generate(false);
  assert.equal(failure.elements.download.disabled, true);
});
