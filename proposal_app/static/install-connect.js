'use strict';

const installConnection = (() => {
  const formMarkup = `<form class="install-connect" data-install-connect>
    <p data-install-account></p>
    <label>安装窗口里的三位连接码
      <input name="pin" type="text" inputmode="numeric" pattern="[0-9]{3}" maxlength="3" placeholder="例如 037" autocomplete="off" required>
    </label>
    <button type="submit" class="primary" disabled>连接这台电脑</button>
    <p class="install-status" data-install-status role="status">正在检查登录状态…</p>
  </form>`;

  async function request(path, body) {
    const response = await fetch('/api/' + path, body ? {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    } : {cache: 'no-store'});
    if (response.status === 401) throw Error('请先登录开题手记，再回这里连接。');
    const result = await response.json();
    if (!response.ok) throw Error(result.error || '连接暂时无法完成。');
    return result;
  }

  function steps(current) {
    const labels = ['安装插件', '连接账号', '选文件夹'];
    return '<ol class="coach-wizard-steps" aria-label="连接进度">' + labels.map((label, index) => {
      const step = index + 1;
      const complete = step < current;
      return '<li'+(step === current ? ' aria-current="step"' : complete ? ' class="complete"' : '')+'>' +
        '<span class="coach-step-number" aria-hidden="true">'+(complete ? '✓' : step)+'</span>'+label+'</li>';
    }).join('') + '</ol>';
  }

  async function mount(form, onConnected, {forcePair = false, focusPin = false, isActive = () => form.isConnected, onUnavailable} = {}) {
    const status = form.querySelector('[data-install-status]');
    const account = form.querySelector('[data-install-account]');
    const button = form.querySelector('[type=submit]');
    const pin = form.elements.pin;
    function showStatus(message, state = '') {
      status.textContent = message;
      status.dataset.state = state;
    }
    function connected() {
      if (!isActive()) return;
      button.disabled = true;
      pin.disabled = true;
      showStatus('已连接。如果 Codex 正在运行，请先退出，再重新打开。', 'success');
      onConnected?.();
    }
    let user;
    try {
      const state = await request('plugin-connection');
      if (!isActive()) return;
      user = state.user;
      account.textContent = user.name + '（' + (user.role === 'teacher' ? '老师' : '学生') + '）';
      if (state.connected && !forcePair) connected();
      else {
        button.disabled = false;
        showStatus('安装窗口先别关。');
        if (focusPin) pin.focus();
      }
    } catch (error) {
      if (isActive()) {
        showStatus(error.message, 'error');
        onUnavailable?.();
      }
      return;
    }

    form.addEventListener('submit', async event => {
      event.preventDefault();
      event.stopPropagation();
      if (button.disabled || !isActive()) return;
      button.disabled = true;
      showStatus('正在查找安装窗口…');
      let approved = false;
      try {
        let handoff;
        try {
          const response = await fetch('http://127.0.0.1:48767/pairing', {
            cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(5000)
          });
          if (!response.ok) throw Error();
          handoff = await response.json();
        } catch {
          throw Error('找不到安装程序。请确认安装窗口仍打开、网址和当前网页一致。如浏览器询问是否允许访问本机，请允许后重试。');
        }
        if (!isActive()) return;
        const result = await request('plugin/authorize', {device_code: handoff.device_code, pin: pin.value, account: user.id});
        if (!result.authorized) throw Error(result.error);
        approved = true;
        showStatus('已确认，正在连接…');
        for (let attempt = 0; attempt < 60 && isActive(); attempt++) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          if (!isActive()) return;
          const state = await request('plugin-connection');
          if (state.user.id !== user.id) throw Error('教学账号已切换，请重新连接。');
          if (state.connected) { connected(); return; }
        }
        throw Error('还没连接成功。请检查安装窗口，再刷新工作台。');
      } catch (error) {
        showStatus(error.message, 'error');
        if (!approved) button.disabled = false;
      }
    });
  }
  return {formMarkup, mount, steps};
})();

const downloadStatus = document.querySelector('[data-download-status]');
if (downloadStatus) {
  fetch('/api/plugin-downloads', {cache: 'no-store'}).then(response => {
    if (!response.ok) throw Error();
    return response.json();
  }).then(downloads => {
    const platform = ProposalPluginPath.platform();
    let available = false;
    for (const link of document.querySelectorAll('[data-download]')) {
      const target = link.dataset.download;
      if (!downloads[target]) continue;
      link.href = downloads[target];
      link.hidden = false;
      link.classList.toggle('recommended', target === platform);
      const version = link.querySelector('[data-download-version]');
      const publishedVersion = downloads.versions?.[target];
      version.textContent = publishedVersion ? 'v' + publishedVersion : '版本暂不可读';
      version.hidden = false;
      available = true;
    }
    downloadStatus.hidden = available;
    if (!available) downloadStatus.textContent = '本站尚未发布安装包。';
  }).catch(() => { downloadStatus.textContent = '安装包列表暂时无法读取，请刷新重试。'; });
}

const reconnect = document.querySelector('[data-reconnect]');
if (reconnect) {
  const dialog = document.querySelector('[data-reconnect-dialog]');
  const content = dialog.querySelector('[data-reconnect-form]');
  const returnLink = dialog.querySelector('[data-reconnect-return]');
  reconnect.addEventListener('click', () => {
    returnLink.hidden = true;
    content.innerHTML = installConnection.formMarkup;
    const form = content.querySelector('form');
    dialog.showModal();
    installConnection.mount(form, () => {
      const status = document.createElement('p');
      status.setAttribute('role', 'status');
      status.className = 'reconnect-success';
      status.textContent = '已重新连接。';
      const message = document.createElement('p');
      message.textContent = '等安装窗口显示完成。如果 Codex 正在运行，请先退出，再重新打开。';
      content.replaceChildren(status, message);
      returnLink.hidden = false;
      returnLink.focus();
    }, {
      forcePair: true,
      focusPin: true,
      isActive: () => dialog.open && form.isConnected,
      onUnavailable: () => { returnLink.hidden = false; }
    });
  });
}
