const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const paths = require('./static/plugin-path.js');
const existingFolder = 'D:\\我的课题';

test('Windows paths normalize quotes, Chinese, spaces, separators and parent segments', async () => {
  assert.equal(paths.normalize('  "d:/探月科研课程/子目录/../开题 项目/./"  '), 'D:\\探月科研课程\\开题 项目');
  assert.equal(paths.normalize('c:\\..\\..\\课题'), 'C:\\课题');
  assert.equal(paths.normalize('D:\\'), 'D:\\');
  assert.equal(await paths.hash('D:/我的项目/./'), createHash('sha256').update('d:\\我的项目').digest('hex'));
  for (const bad of ['', '开题', 'D:开题', '/开题', '\\\\host\\share', 'D:\\开题?', 'D:\\CON', 'D:\\con.txt', 'D:\\aux\\child', 'D:\\COM¹', 'D:\\LPT9.txt', 'D:\\name.', 'D:\\name \\child', 'D:\\file:stream', 'D:\\bad\nname', '"D:\\foo']) {
    assert.throws(() => paths.normalize(bad), /完整的 Windows/);
  }
});

test('deep links preserve path and prompt independently and validate thread ID', () => {
  const thread = '00000000-0000-0000-0000-000000000001';
  const prompt = '$proposal-coach:research-proposal-coach 项目 & 版本=#123\n请读最新状态';
  const link = new URL(paths.link({thread_id: thread, prompt}, 'D:\\课题 & 空格'));
  assert.equal(link.pathname, '/' + thread);
  assert.equal(link.searchParams.get('path'), 'D:\\课题 & 空格');
  assert.equal(link.searchParams.get('prompt'), prompt);
  assert.throws(() => paths.link({thread_id: '../new?x', prompt}, 'D:\\课题'));
});

function dialogHarness({thread = null, remembered = null, opened = null, role = 'student', os = 'windows'} = {}) {
  const source = fs.readFileSync(__dirname + '/static/app.js', 'utf8');
  const start = source.indexOf('async function launchPluginDialog(');
  const end = source.indexOf("sheet.addEventListener('close'", start);
  const nodes = new Map();
  function node(selector) {
    if (!nodes.has(selector)) nodes.set(selector, {
      value: '', textContent: '', isConnected: true, events: {},
      addEventListener(event, fn) { this.events[event] = fn; },
      setAttribute(name, val) { this[name] = val; }, removeAttribute(name) { delete this[name]; }, focus() {},
    });
    return nodes.get(selector);
  }
  const key = 'proposal-' + os + '-folder:U1:P1';
  const storage = new Map();
  if (remembered) storage.set(key, remembered);
  if (opened) storage.set(key + ':opened-hash', opened);
  const requests = [];
  const timers = [];
  const context = {
    navigator: {platform: os === 'macos' ? 'MacIntel' : 'Win32'},
    state: {user: {id: 'U1'}, project: {id: 'P1', plugin_pilot: {download: '/plugin.zip'}}},
    teacher: () => role === 'teacher', safeUrl: x => x,
    sheet: {open: true, querySelector: node, close() { this.open = false; }}, ProposalPluginPath: {...paths},
    setTimeout: callback => timers.push(callback),
    dialog(title, body) { context.title = title; context.body = body; context.sheet.open = true; },
    notify() {},
    localStorage: {getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v)},
    window: {location: {href: ''}},
    async api(endpoint, body) {
      if (endpoint === 'plugin-connection') return {connected: true};
      requests.push({endpoint, body});
      return {thread_id: body.recovery ? null : thread, prompt: `version=${requests.length} workspace_hash=${body.workspace_hash}`};
    },
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  return {context, requests, node, storage, key, timers, launch: (...args) => context.launchPluginDialog(...args)};
}

test('new projects start without a shared path and send only the normalized hash', async () => {
  const h = dialogHarness();
  await h.launch();
  const folder = h.node('[data-pilot-folder]');
  assert.equal(folder.value, '');
  folder.value = 'D:bad';
  folder.events.blur();
  assert.equal(folder['aria-invalid'], 'true');
  await h.node('[data-pilot-open]').events.click();
  assert.equal(h.requests.length, 0);
  folder.value = '"D:/课题 & 空格/./"';
  folder.events.blur();
  assert.equal(folder.value, 'D:\\课题 & 空格');
  await h.node('[data-pilot-open]').events.click();
  assert.equal(h.requests.length, 1);
  assert.deepEqual(Object.keys(h.requests[0].body).sort(), ['recovery', 'workspace_hash']);
  assert.equal(h.requests[0].body.workspace_hash, await paths.hash(folder.value));
  assert.equal(new URL(h.context.window.location.href).searchParams.get('path'), folder.value);
  await h.node('[data-pilot-open]').events.click();
  assert.match(new URL(h.context.window.location.href).searchParams.get('prompt'), /version=2/);
});

test('same-folder continuation reuses thread; path changes require independent recovery', async () => {
  const thread = '00000000-0000-0000-0000-000000000001';
  const h = dialogHarness({thread, remembered: existingFolder, opened: await paths.hash(existingFolder)});
  await h.launch();
  assert.equal(h.context.title, '打开 Codex');
  assert.match(h.context.body, /<details[^>]*data-pilot-help><summary>如果打不开 Codex 或原来的讨论<\/summary>.*更换课题文件夹/);
  assert.equal(h.requests[0].body.reuse, true);
  assert.equal(new URL(h.context.window.location.href).pathname, '/' + thread);
  h.node('[data-pilot-change-folder]').events.click();
  assert.equal(h.context.title, '选择课题文件夹');
  assert.equal(h.node('[data-pilot-help]').open, true);
  assert.equal(h.requests.length, 1);
  h.node('[data-pilot-folder]').value = 'E:\\新课题';
  await h.node('[data-pilot-open]').events.click();
  assert.equal(h.requests.length, 2);
  assert.match(h.node('#pilot-path-error').textContent, /恢复本机讨论/);
  await h.node('[data-pilot-recover]').events.click();
  assert.equal(h.requests[2].body.recovery, true);
  assert.equal(new URL(h.context.window.location.href).pathname, '/new');
});

test('student next stage and teacher next submission reuse a verified folder but receive a new chat', async () => {
  for(const role of ['student','teacher']){
    const h=dialogHarness({role,remembered:existingFolder,opened:await paths.hash(existingFolder)});
    await h.launch();
    assert.equal(h.context.title,'打开 Codex');
    assert.match(h.context.body,role==='student'?/更换课题文件夹/:/更换审阅文件夹/);
    assert.equal(h.requests[0].body.reuse,true);
    assert.equal(new URL(h.context.window.location.href).pathname,'/new');
    if(role==='teacher'){
      h.node('[data-pilot-change-folder]').events.click();
      assert.equal(h.context.title,'选择审阅文件夹');
      assert.equal(h.node('[data-pilot-help]').open,true);
      assert.equal(h.requests.length,1);
    }
  }
});

test('a directory no longer verified on this device falls back to the chooser', async () => {
  const h=dialogHarness({remembered:existingFolder,opened:await paths.hash(existingFolder)});
  const normal=h.context.api;
  h.context.api=(endpoint,body)=>body?.reuse
    ? Promise.reject(Object.assign(Error('请重新选择这台电脑上的文件夹。'),{code:'workspace_reselection_required'}))
    : normal(endpoint,body);
  await h.launch();
  assert.equal(h.context.title,'选择课题文件夹');
  assert.equal(h.node('#pilot-path-error').textContent,'请重新选择这台电脑上的文件夹。');
  assert.equal(h.context.window.location.href,'');
});

test('lost browser mapping never unconditionally opens existing conversation; teacher uses same plugin', async () => {
  const h = dialogHarness({thread: '00000000-0000-0000-0000-000000000001', role: 'teacher', remembered: existingFolder});
  await h.launch();
  assert.equal(h.context.title, '选择审阅文件夹');
  assert.match(h.context.body, /审阅文件夹/);
  await h.node('[data-pilot-open]').events.click();
  assert.equal(h.context.window.location.href, '');
  assert.match(h.node('#pilot-path-error').textContent, /恢复本机讨论/);
  await h.node('[data-pilot-recover]').events.click();
  assert.equal(h.requests.at(-1).body.recovery, true);
});

test('macOS starts with an empty folder, sends only its case-sensitive hash, and opens an absolute POSIX path', async () => {
  const h = dialogHarness({os: 'macos'});
  const path = '/Users/Lin/Documents/开题 Café';
  const entered = '/Users/Lin/Desktop/../Documents/开题 Cafe\u0301';
  const expected = createHash('sha256').update('macos:' + path).digest('hex');
  await h.launch();
  const folder = h.node('[data-pilot-folder]');
  assert.equal(folder.value, '');
  assert.doesNotMatch(h.context.body, /新建文件夹/);
  folder.value = 'D:/课题';
  folder.events.blur();
  assert.equal(folder['aria-invalid'], 'true');
  folder.value = entered;
  await h.node('[data-pilot-open]').events.click();
  assert.deepEqual(JSON.parse(JSON.stringify(h.requests[0].body)), {workspace_hash: expected, recovery: false});
  assert.equal(new URL(h.context.window.location.href).searchParams.get('path'), '/Users/Lin/Documents/开题 Cafe\u0301');
  assert.notEqual(await paths.hash(path.toLowerCase(), 'macos'), expected);
});

test('folder and launch dialogs close only when the new chat reports a verified binding', async () => {
  for (const opened of [null, await paths.hash(existingFolder)]) {
    const h = dialogHarness({remembered: existingFolder, opened});
    const originalApi = h.context.api;
    let bound = false;
    h.context.api = async (endpoint, body) => {
      if (endpoint.startsWith('plugin-entry-status/')) return {bound};
      const data = await originalApi(endpoint, body);
      return body ? {...data, stage_session:'a'.repeat(32), watch_open:true} : data;
    };
    await h.launch();
    if (!opened) await h.node('[data-pilot-open]').events.click();
    assert.equal(h.context.sheet.open, true);
    h.timers.shift()();
    await new Promise(setImmediate);
    assert.equal(h.context.sheet.open, true);
    bound = true;
    h.timers.shift()();
    await new Promise(setImmediate);
    assert.equal(h.context.sheet.open, false);
  }
});

test('the native folder chooser can be reopened after a conflict', async () => {
  const h = dialogHarness();
  const modes = [];
  const choose = h.node('[data-pilot-choose]');
  choose.focus = () => { choose.focused = true; };
  h.context.ProposalPluginPath.pick = async mode => {
    modes.push(mode);
    return modes.length === 1 ? 'D:/课题/已使用' : 'D:/课题/新观察';
  };
  await h.launch();
  const folder = h.node('[data-pilot-folder]');
  await choose.events.click();
  assert.equal(folder.value, 'D:\\课题\\已使用');
  h.context.api = async () => { throw Object.assign(Error('已用于另一个课题'), {code:'workspace_in_use'}); };
  await h.node('[data-pilot-open]').events.click();
  assert.equal(choose.focused, true);
  assert.equal(folder['aria-invalid'], 'true');
  await choose.events.click();
  assert.deepEqual(modes, ['choose', 'choose']);
  assert.equal(folder.value, 'D:\\课题\\新观察');
  assert.equal(folder['aria-invalid'], undefined);
});

test('learning record reports receipt and pending state without claiming all local turns synchronized', () => {
  const source = fs.readFileSync(__dirname + '/static/app.js', 'utf8');
  const start = source.indexOf('function learningView() {');
  const end = source.indexOf('document.addEventListener("click"', start);
  const context = {state: {project: {}, discussions: {}}, esc: String, dateText: String, btn: () => '', names: []};
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  context.state.discussions.sync = {status: 'unconfirmed'};
  assert.match(context.learningView(), /讨论开始后，原话会同步到这里/);
  context.state.discussions.sync = {status: 'received', last_complete_turn: 'synthetic-turn', last_receipt_at: '2026-11-20T01:00:00Z'};
  assert.doesNotMatch(context.learningView(), /synthetic-turn/);
  assert.match(context.learningView(), /最近同步 2026-11-20T01:00:00Z/);
  context.state.discussions.sync.status = 'syncing';
  assert.match(context.learningView(), /最近一轮的回复还在同步/);
});
