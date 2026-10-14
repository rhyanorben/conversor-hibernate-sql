import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createApi } from '../hibernate_sql/presentation/web/api.js';
import { createController } from '../hibernate_sql/presentation/web/controller.js';

function element() {
  return {
    value: '', disabled: false, textContent: '', className: '', options: [],
    focus() { this.focused = true; },
    select() { this.selected = true; },
    append(option) { this.options.push(option); this.value ||= option.value; },
  };
}

function setup(overrides = {}) {
  const elements = Object.fromEntries(
    ['logs', 'output', 'status', 'prefix', 'normal', 'command', 'clear', 'copy']
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
  const controller = createController(elements, api, clipboard, label => ({ value: label, textContent: label }));
  return { elements, controller, requests, copied };
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
  const previous = {
    document: globalThis.document,
    window: globalThis.window,
    navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
  };
  try {
    globalThis.document = {
      getElementById: id => state.elements[id],
      createElement: () => ({}),
    };
    globalThis.window = { fetch: async () => ({ ok: true, json: async () => ['EXPLAIN'] }) };
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: {} } });
    await import('../hibernate_sql/presentation/web/app.js');
    assert.equal(state.elements.prefix.options[0].value, 'EXPLAIN');
    assert.equal(typeof state.elements.normal.onclick, 'function');
  } finally {
    if (previous.document === undefined) delete globalThis.document;
    else globalThis.document = previous.document;
    if (previous.window === undefined) delete globalThis.window;
    else globalThis.window = previous.window;
    if (previous.navigator) Object.defineProperty(globalThis, 'navigator', previous.navigator);
    else delete globalThis.navigator;
  }
});
