"use strict";
// The full path stays in this browser and the Codex deep link, never in site requests.
const ProposalPluginPath = (() => {
  const error = '请输入完整的 Windows 文件夹路径，例如 D:\\科研课程\\我的课题';
  function platform(browser = globalThis.navigator) {
    return /^mac/i.test(browser?.userAgentData?.platform || browser?.platform || '') &&
      !(browser?.maxTouchPoints > 1) ? 'macos' : 'windows';
  }
  function normalize(value, os = 'windows') {
    let path = String(value ?? '').trim();
    if (path.startsWith('"') && path.endsWith('"')) path = path.slice(1, -1);
    if (os === 'macos') {
      if (!/^\/(?!\/)/.test(path) || /[\x00-\x1f]/.test(path)) {
        throw Error('请输入完整的 macOS 文件夹路径，例如 /Users/你的用户名/Documents/开题');
      }
      const parts = [];
      for (const part of path.split('/')) {
        if (!part || part === '.') continue;
        if (part === '..') parts.pop();
        else parts.push(part);
      }
      if (!parts.length) throw Error('请选择单独的课题文件夹。');
      return '/' + parts.join('/');
    }
    path = path.replace(/\//g, '\\');
    if (!/^[a-z]:\\/i.test(path) || /[\x00-\x1f"<>|?*]/.test(path) || path.slice(2).includes(':')) throw Error(error);
    const parts = [];
    for (const part of path.slice(3).split('\\')) {
      if (!part || part === '.') continue;
      if (part === '..') { parts.pop(); continue; }
      const deviceName = part.split('.')[0].replace(/ +$/, '');
      if (/[. ]$/.test(part) || /^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])$/i.test(deviceName)) throw Error(error);
      parts.push(part);
    }
    return path[0].toUpperCase() + ':\\' + parts.join('\\');
  }
  async function hash(path, os = 'windows') {
    const normalized = normalize(path, os);
    const key = os === 'macos' ? 'macos:' + normalized.normalize('NFC') : normalized.toLowerCase();
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key));
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
  }
  function link(entry, path, os = 'windows') {
    if (entry.thread_id && !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(entry.thread_id)) throw Error('讨论地址无效，请重试。');
    if (!entry.prompt) throw Error('讨论指令尚未准备好，请重试。');
    return `codex://threads/${entry.thread_id || 'new'}?path=${encodeURIComponent(normalize(path, os))}&prompt=${encodeURIComponent(entry.prompt)}`;
  }
  async function pick(mode, isActive) {
    const nonce = Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, '0')).join('');
    const endpoint = 'http://127.0.0.1:48768/folder/' + nonce;
    window.location.href = 'research-coach-folder://' + mode + '/' + nonce;
    const started = Date.now();
    let reachable = false;
    while (isActive() && Date.now() - started < (reachable ? 175000 : 25000)) {
      let response;
      try {
        response = await fetch(endpoint, {cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(1400)});
      } catch { /* The native helper may still be starting. */ }
      if (response?.ok) {
        reachable = true;
        if (response.status === 200) {
          const selection = await response.json();
          if (selection.error) throw Error(selection.error);
          return selection.path;
        }
      }
      await new Promise(resolve => setTimeout(resolve, reachable ? 650 : 400));
    }
    if (!isActive()) return null;
    if (reachable) throw Error('选择文件夹超时，请再试一次。');
    throw Object.assign(Error('没有收到本机文件夹窗口的响应。请确认已安装新版插件，并允许浏览器打开助手和访问本机。'), {code:'folder_helper_unavailable'});
  }
  return {platform, normalize, hash, link, pick};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ProposalPluginPath;
