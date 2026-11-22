const statusLine = document.getElementById('connection-status');
const form = document.getElementById('connection-login');
const approve = document.getElementById('approve-device');
const switchAccount = document.getElementById('switch-account');
const device = new URLSearchParams(location.search).get('device');

async function call(path, body) {
  const response = await fetch(`/api/${path}`, body ? { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw Error(data.error);
  return data;
}

function show(user) {
  delete statusLine.dataset.state;
  form.hidden = Boolean(user);
  approve.hidden = !['student', 'teacher'].includes(user?.role);
  switchAccount.hidden = !user;
  statusLine.textContent = !user ? '请先用你的教学账号登录。' : user.role === 'teacher'
    ? `当前账号：${user.name}（老师）。确认后，可在这台电脑辅助审阅。`
    : user.role === 'student' ? `当前账号：${user.name}（学生）。确认后，可在这台电脑讨论并同步记录。` : '请切换到学生或老师账号。';
}

function showError(message) {
  statusLine.dataset.state = 'error';
  statusLine.textContent = message;
}

switchAccount.addEventListener('click', async () => {
  switchAccount.disabled = true;
  try { await call('logout', {}); show(null); form.querySelector('[name=username]').focus(); }
  catch (error) { showError(error.message); }
  finally { switchAccount.disabled = false; }
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  try { show((await call('login', Object.fromEntries(new FormData(form)))).user); form.reset(); }
  catch (error) { showError(error.message); }
});

approve.addEventListener('click', async () => {
  approve.disabled = true;
  try {
    await call('plugin/authorize', { device_code: device });
    approve.hidden = true;
    switchAccount.hidden = true;
    statusLine.dataset.state = 'success';
    statusLine.textContent = '已获准连接。等安装窗口显示完成，再回课题页。';
  } catch (error) { showError(error.message); }
  finally { approve.disabled = false; }
});

if (device && /^[A-Za-z0-9_-]{32}$/.test(device)) call('me').then(data => show(data.user)).catch(error => showError(error.message));
else showError('连接链接无效。请重新运行「安装开题手记」。');
