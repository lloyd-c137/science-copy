// Exercise the real browser-to-Windows handoff against an isolated teaching site.
const assert = require('node:assert/strict');
const { createHash, randomUUID } = require('node:crypto');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const output = fs.mkdtempSync(path.join(os.tmpdir(), 'research-coach-install-'));
const packagePath = path.join(root, 'deliverables', 'research-coach-windows-8767.zip');
const macPackagePath = path.join(root, 'deliverables', 'research-coach-macos-8767.zip');
const children = [];
let browser;

function python(args) {
  const child = spawn('python', ['-B', ...args], {
    cwd: root, env: {...process.env, PYTHONIOENCODING: 'utf-8'}, windowsHide: true
  });
  children.push(child);
  let stdout = '';
  child.stdout.setEncoding('utf8').on('data', data => { stdout += data; });
  child.stderr.setEncoding('utf8').on('data', data => {
    if (!data.includes('HTTP/1.1')) process.stderr.write(data);
  });
  return {child, stdout: () => stdout};
}

async function waitFor(process, pattern) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const match = process.stdout().match(pattern);
    if (match) return match[1];
    if (process.child.exitCode !== null) throw Error(process.stdout());
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error('Process did not become ready: ' + process.stdout());
}

async function run() {
  const db = path.join(output, 'site.sqlite3');
  const service = python(['-c', `
import json, sys
from proposal_app import server
with server.serve(sys.argv[1], 0, plugin_origin='http://127.0.0.1', plugin_package=sys.argv[2], plugin_macos_package=sys.argv[3]) as app:
    app.plugin_origin += ':' + str(app.server_port)
    with server.connect(sys.argv[1]) as db:
        pid, data = db.execute("SELECT id, card FROM projects WHERE student='U3'").fetchone()
        card = json.loads(data)
        card.update(status='review', current_step=6)
        db.execute('UPDATE projects SET card=? WHERE id=?', (json.dumps(card), pid))
    print('ORIGIN=' + app.plugin_origin, flush=True)
    app.serve_forever()
`, db, packagePath, macPackagePath]);
  const origin = await waitFor(service, /ORIGIN=(http:\/\/127\.0\.0\.1:\d+)/);
  browser = await chromium.launch({channel: 'chrome', headless: true});
  for (const role of ['student', 'teacher']) {
    const context = await browser.newContext({viewport: {width: 390, height: 844}});
    let helperFolder;
    await context.route('**/plugin-path.js', async route => {
      const response = await route.fetch();
      const source = await response.text();
      await route.fulfill({response, body: source.replace(
        "window.location.href = 'research-coach-folder://'",
        "window.folderProtocol = 'research-coach-folder://'")});
    });
    await context.route('http://127.0.0.1:48768/folder/**', route => route.fulfill({
      headers: {'Access-Control-Allow-Origin': origin}, json: {path: helperFolder}
    }));
    await context.route('**/app.js', async route => {
      const response = await route.fetch();
      const source = await response.text();
      assert.ok(source.includes('window.location.href = url;'));
      await route.fulfill({response, body: source.replaceAll('window.location.href = url;',
        '(window.launchedCodex ||= []).push(url);')});
    });
    const page = await context.newPage();
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    const login = await context.request.post(origin + '/api/login', {data: {username: role, password: 'yanjiu123'}});
    assert.equal(login.status(), 200);
    const home = await (await context.request.get(origin + '/api/home')).json();
    const project = home.projects.find(row => row.status === (role === 'teacher' ? 'review' : 'active'));
    assert.ok(project);
    const route = origin + '/api/projects/' + project.id + '/plugin-entry';
    const payload = {data: {workspace_hash: 'a'.repeat(64)}};
    assert.equal((await context.request.post(route, payload)).status(), 409);
    await page.goto(origin + '/?project=' + project.id);
    const launch = page.locator(role === 'teacher' ? 'button[data-action="review-coach"]' : 'button[data-action="launch"]').first();
    await launch.waitFor();
    assert.equal(await launch.isEnabled(), true);
    assert.equal(await page.getByRole('button', {name: '首次连接'}).count(), 0);
    await launch.click();
    await page.locator('[aria-current="step"]').getByText('安装插件').waitFor();
    await page.getByRole('link', {name:'下载 Windows 安装包'}).waitFor();
    await page.getByRole('link', {name:'下载 macOS 安装包'}).waitFor();
    const installer = python(['-c', `
import sys
from pathlib import Path
from unittest.mock import patch
from proposal_app import pilot_client
pilot_client.Journal(Path(sys.argv[2]) / 'archives.sqlite3').remember(
    pilot_client.mcp.Client(sys.argv[1], account=sys.argv[3]).owner, 'old-stage', 'old-log',
    'D:/Projects/Prior', project='P-old-local-only')
with patch.object(pilot_client.pilot_defaults, 'sync'):
    pilot_client.pair(sys.argv[1], Path(sys.argv[2]), local=True)
`, origin, path.join(output, role), (await login.json()).user.id]);
    const pin = await waitFor(installer, /连接码：(\d{3})/);
    await page.getByRole('button', {name:'我已有三位连接码'}).click();
    await page.locator('[aria-current="step"]').getByText('连接账号').waitFor();
    await page.getByRole('button', {name:'返回安装'}).click();
    await page.locator('[aria-current="step"]').getByText('安装插件').waitFor();
    await page.getByRole('button', {name:'我已有三位连接码'}).click();
    const input = page.getByLabel('安装窗口里的三位连接码');
    const confirm = page.getByRole('button', {name: '连接这台电脑', exact: true});
    await input.fill(pin === '000' ? '001' : '000');
    assert.equal(await page.getByRole('button', {name:'重新连接', exact:true}).count(), 0);
    await confirm.click();
    await page.getByText('连接码不正确，请核对安装窗口。', {exact: true}).waitFor();
    assert.equal(await page.locator('[data-pilot-folder]').count(), 0);
    await input.fill(pin);
    await confirm.click();
    await page.locator('[aria-current="step"]').getByText('选文件夹').waitFor();
    await page.locator('[data-pilot-folder]').waitFor();
    assert.equal(await page.getByText('已连接。安装完成后，如果 Codex 正在运行，请先退出，再重新打开。').isVisible(), true);
    const folder = page.locator('[data-pilot-folder]');
    helperFolder = 'd:/Projects/Prior';
    await page.getByRole('button', {name:'选择文件夹', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('[data-pilot-folder]').value === 'D:\\Projects\\Prior');
    assert.match(await page.evaluate(() => window.folderProtocol), /^research-coach-folder:\/\/choose\/[0-9a-f]{48}$/);
    const rejected = page.waitForResponse(response => response.url() === route && response.request().method() === 'POST');
    await page.getByRole('button', {name:'打开 Codex', exact:true}).click();
    assert.equal((await rejected).status(), 409);
    await page.getByText('这个文件夹已用于另一个课题。请点「选择文件夹」换一个。', {exact:true}).waitFor();
    assert.equal(await folder.getAttribute('aria-invalid'), 'true');
    assert.equal(await page.getByRole('button', {name:'选择文件夹', exact:true}).evaluate(el => document.activeElement === el), true);
    assert.equal(await page.evaluate(() => window.launchedCodex?.length || 0), 0);
    helperFolder = 'D:/Projects/Independent';
    assert.equal(await page.getByRole('button', {name:'新建文件夹', exact:true}).count(), 0);
    await page.getByRole('button', {name:'选择文件夹', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('[data-pilot-folder]').value === 'D:\\Projects\\Independent');
    assert.match(await page.evaluate(() => window.folderProtocol), /^research-coach-folder:\/\/choose\/[0-9a-f]{48}$/);
    const accepted = page.waitForResponse(response => response.url() === route && response.request().method() === 'POST');
    await page.getByRole('button', {name:'打开 Codex', exact:true}).click();
    assert.equal((await accepted).status(), 200);
    await page.getByText('已请求打开 Codex。', {exact:true}).waitFor();
    assert.equal(await page.evaluate(() => window.launchedCodex.length), 1);
    assert.equal(await page.getByRole('button', {name:'恢复本机讨论'}).count(), 0);
    await page.getByText('如果打不开 Codex 或原来的讨论', {exact:true}).click();
    assert.equal(await page.getByRole('button', {name:'恢复本机讨论'}).isVisible(), true);
    assert.equal(await page.getByRole('button', {name:'重新连接 Codex'}).isVisible(), true);
    assert.equal((await (await context.request.get(origin + '/api/plugin-connection')).json()).connected, true);
    await page.getByRole('button', {name:'关闭', exact:true}).click();
    await launch.click();
    await page.locator('[data-pilot-folder]').waitFor();
    assert.equal(await page.locator('.coach-wizard-steps').count(), 0);
    const folderHash=createHash('sha256').update('d:\\projects\\independent').digest('hex');
    const currentFolder={data:{workspace_hash:folderHash}};
    const entry = await context.request.post(route, currentFolder);
    assert.equal(entry.status(), 200);
    const details = await entry.json();
    const lines = details.prompt.split('\n');
    assert.equal(lines.length, 3);
    assert.equal(lines[0], '$research-coach:research-proposal-' + (role === 'teacher' ? 'review' : 'coach'));
    assert.match(lines[1], /^开题手记会话：[a-f0-9]{32}$/);
    assert.match(lines[2], /^请/);
    assert.deepEqual(failures, []);
    if (installer.child.exitCode === null) await once(installer.child, 'exit');
    assert.equal(installer.child.exitCode, 0);
    const receiptUrl = origin + '/api/plugin-entry-status/' + details.stage_session;
    assert.equal(details.watch_open, true);
    assert.deepEqual(await (await context.request.get(receiptUrl)).json(), {bound: false});
    const device = JSON.parse(fs.readFileSync(path.join(output, role, 'device.json'), 'utf8'));
    const thread=randomUUID();
    const binding = await context.request.post(origin + '/api/plugin/session', {
      headers: {Authorization:'Bearer ' + device.token},
      data: {stage_session:details.stage_session, thread, workspace_hash:folderHash}
    });
    assert.equal(binding.status(), 200);
    assert.deepEqual(await (await context.request.get(receiptUrl)).json(), {bound: true});
    assert.equal((await context.request.post(route, currentFolder)).ok(), true);
    await page.getByRole('button', {name:'关闭', exact:true}).click();
    await launch.click();
    await page.waitForFunction(expected=>window.launchedCodex.at(-1)?.includes('/'+expected+'?'), thread);
    assert.equal(await page.locator('#sheet[open] [data-pilot-folder]').count(),0);
    await page.goto(origin + '/first-use.html');
    const {versions} = await (await context.request.get(origin + '/api/plugin-downloads')).json();
    for (const [target, resource] of [['windows', packagePath], ['macos', macPackagePath]]) {
      const download = page.locator('[data-download="' + target + '"]');
      await download.waitFor();
      const response = await context.request.get(origin + await download.getAttribute('href'));
      assert.equal(response.status(), 200);
      assert.equal(response.headers()['content-type'], 'application/zip');
      assert.deepEqual(await response.body(), fs.readFileSync(resource));
      assert.match(versions[target], /^\d+\.\d+\.\d+/);
      assert.equal(await download.locator('[data-download-version]').innerText(), 'v' + versions[target]);
    }
    await page.locator('img').evaluateAll(images => Promise.all(images.map(img => img.decode())));
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({width, height: 880});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    }
    const reconnect = python(['-c', `
import sys
from pathlib import Path
from unittest.mock import patch
from proposal_app import pilot_client
with patch.object(pilot_client.pilot_defaults, 'sync'):
    pilot_client.pair(sys.argv[1], Path(sys.argv[2]), local=True)
`, origin, path.join(output, role)]);
    const renewedPin = await waitFor(reconnect, /连接码：(\d{3})/);
    await page.getByRole('button', {name:'重新连接', exact:true}).click();
    await page.getByRole('button', {name:'连接这台电脑', exact:true}).waitFor();
    await page.getByLabel('安装窗口里的三位连接码').fill(renewedPin);
    await page.getByRole('button', {name:'连接这台电脑', exact:true}).click();
    await page.getByText('已重新连接。', {exact:true}).waitFor();
    assert.equal((await (await context.request.get(origin + '/api/plugin-connection')).json()).connected, true);
    const renewedDevice = JSON.parse(fs.readFileSync(path.join(output, role, 'device.json'), 'utf8'));
    assert.notEqual(renewedDevice.token, device.token);
    assert.equal((await context.request.post(origin + '/api/plugin/runtime-settings', {
      headers: {Authorization:'Bearer ' + device.token}, data:{}
    })).status(), 401);
    assert.deepEqual(failures, []);
    await context.close();
    console.log(role + ': start button, wizard steps, wrong PIN, automatic folder selection, connected shortcut, downloads and mobile layout passed');
  }
}

run().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  for (const child of children) {
    if (child.exitCode === null) { child.kill(); await once(child, 'exit'); }
  }
  fs.rmSync(output, {recursive: true, force: true});
});
