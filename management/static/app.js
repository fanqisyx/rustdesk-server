'use strict';
const $ = selector => document.querySelector(selector);
let token = '', me = null, data = {devices: [], groups: [], users: [], grants: [], audit: [], shares: []};
let moveId = '', passwordId = null;
let registering = false;
let shareDeviceId = '';
const permissionNames = {view: '查看', connect: '远程桌面', file_transfer: '文件传输', terminal: '终端', tunnel: '隧道 / RDP', camera: '摄像头'};
const eventNames = {'login': '登录成功', 'login.denied': '登录失败', 'logout': '退出登录', 'user.create': '创建账号', 'user.disable': '停用账号', 'user.enable': '启用账号', 'user.password_reset': '重设密码', 'group.create': '创建分组', 'group.delete': '删除分组', 'device.create': '登记设备', 'device.update': '更新设备', 'device.rotate_token': '更新设备凭据', 'grant.save': '保存授权', 'grant.revoke': '撤销授权', 'ticket.issue': '签发连接票据', 'ticket.denied': '拒绝连接票据', 'connection.authorized': '连接权限校验通过', 'connection.denied': '拒绝连接授权'};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const time = value => value ? new Date(value * 1000).toLocaleString() : '—';
eventNames['user.register'] = '自助注册账号';
eventNames['share.save'] = '保存设备分享';
eventNames['share.revoke'] = '撤销设备分享';
permissionNames.share = '允许分享';
permissionNames.view = '查看设备目录';
function notice(message = '', error = false) { $('#notice').textContent = message; $('#notice').classList.toggle('error', error); }
function registrationMode(enabled) {
  registering = enabled;
  const form = $('#login-form');
  $('#display-name-field').hidden = !enabled;
  $('#password-confirmation-field').hidden = !enabled;
  form.display_name.disabled = !enabled;
  form.password_confirmation.disabled = !enabled;
  form.password_confirmation.required = enabled;
  form.password.minLength = enabled ? 12 : 0;
  form.password.autocomplete = enabled ? 'new-password' : 'current-password';
  form.password.value = ''; form.password_confirmation.value = '';
  $('#account-submit').textContent = enabled ? '注册并登录' : '登录管理台';
  $('#toggle-registration').textContent = enabled ? '返回登录' : '注册公司账号';
  $('#account-hint').textContent = enabled ? '密码至少 12 位。注册后自动登录，设备权限需由管理员分配。' : '使用公司账号登录，也可以自行注册。设备权限由管理员分配。';
}
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})}, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000)});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token) clearSession();
    const requestErrors = {
      'Username is already registered': '该账号已注册，请更换账号或返回登录。',
      'Account registration is disabled; contact your administrator': '服务器已关闭自助注册，请联系管理员。',
      'Too many registration attempts; retry in 15 minutes': '注册尝试过于频繁，请在 15 分钟后重试。',
      'Recipient account is unavailable': '接收者账号不存在或已停用。',
      'Device sharing permission is required': '没有分享此设备的权限，请联系管理员。',
      'Cannot share this device or grant permissions you do not have': '设备不可分享，或分享权限超出你当前已有的权限。',
      'Choose another user to share with': '请选择其他用户作为接收者。',
      'Share expiry must be in the future': '分享的到期时间必须晚于当前时间。',
    };
    throw new Error(requestErrors[result.error] || result.error || `HTTP ${response.status}`);
  }
  return result;
}
function clearSession() {
  token = ''; me = null; data = {devices: [], groups: [], users: [], grants: [], audit: [], shares: []};
  $('#workspace').hidden = true; $('#login').hidden = false; $('#identity').textContent = '';
  for (const id of ['device-rows', 'group-list', 'user-list', 'grant-list', 'audit-rows', 'stats', 'share-list']) $('#' + id).replaceChildren();
  $('#secret-text').textContent = ''; document.querySelectorAll('dialog[open]').forEach(d => d.close());
}
function tab(name) {
  document.querySelectorAll('[data-panel]').forEach(el => el.hidden = el.dataset.panel !== name);
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === name));
}
function options(items, selected, placeholder) {
  return (placeholder === undefined ? '' : `<option value="">${esc(placeholder)}</option>`) + items.map(item => `<option value="${esc(item.id)}" ${String(selected) === String(item.id) ? 'selected' : ''}>${esc(item.path || item.display_name || item.name)}</option>`).join('');
}
function groupName(id) { return data.groups.find(g => g.id === id)?.path || id; }
function userName(id) { return data.users.find(u => u.id === id)?.display_name || id; }
async function load() {
  const paths = me.is_admin ? ['/api/admin/devices', '/api/admin/groups', '/api/admin/users', '/api/admin/grants', '/api/admin/audit'] : ['/api/peers?pageSize=200', '/api/device-group/accessible?pageSize=200'];
  const result = await Promise.all(paths.map(p => api(p)));
  if (me.is_admin) [data.devices, data.groups, data.users, data.grants, data.audit] = result;
  else {
    // Follow server pagination so large company directories remain complete.
    const collect = async (path, first) => {
      const rows = [...first.data];
      for (let current = 2; rows.length < first.total; current++) rows.push(...(await api(`${path}?pageSize=200&current=${current}`)).data);
      return rows;
    };
    data.devices = await collect('/api/peers', result[0]);
    data.groups = await collect('/api/device-group/accessible', result[1]);
  }
  data.shares = await api('/api/device-shares');
  document.querySelectorAll('[data-admin]').forEach(el => el.hidden = !me.is_admin);
  const selected = $('#group-filter').value;
  $('#group-filter').innerHTML = options(data.groups, selected, '全部分组');
  document.querySelectorAll('.group-select').forEach(el => el.innerHTML = options(data.groups, el.value, '请选择分组'));
  $('#parent-group').innerHTML = options(data.groups, $('#parent-group').value, '作为根分组');
  $('#grant-user').innerHTML = options(data.users.filter(u => !u.is_admin), $('#grant-user').value, '请选择员工');
  $('#stats').innerHTML = `<div class="stat"><b>${data.devices.filter(d => d.enabled).length}</b><span>可用设备</span></div><div class="stat"><b>${data.groups.filter(g => g.scope === 'internal').length}</b><span>内部资产分组</span></div><div class="stat"><b>${data.groups.filter(g => g.scope === 'external').length}</b><span>外部客户分组</span></div>`;
  renderDevices();
  $('#group-list').innerHTML = data.groups.map(g => `<div class="list-item"><div>${esc(g.path)}<small>${g.scope === 'internal' ? '内部固定资产' : '外部客户设备'}</small></div><button class="secondary" data-action="delete-group" data-id="${g.id}">删除空组</button></div>`).join('') || '<p class="muted">先创建内部资产和外部客户两个根分组。</p>';
  $('#user-list').innerHTML = data.users.map(u => `<div class="list-item"><div>${esc(u.display_name)} <span class="badge ${u.status ? '' : 'off'}">${u.status ? '已启用' : '已停用'}</span><small>${esc(u.name)} · ${u.is_admin ? '管理员' : '员工'}</small></div><div><button class="secondary" data-action="password" data-id="${u.id}">重设密码</button> <button class="secondary" data-action="toggle-user" data-id="${u.id}" ${u.id === me.id ? 'disabled' : ''}>${u.status ? '停用' : '启用'}</button></div></div>`).join('');
  $('#grant-list').innerHTML = data.grants.map(g => `<div class="list-item"><div><b>${esc(userName(g.user_id))}</b> → ${esc(groupName(g.group_id))}<small>${g.permissions.map(p => permissionNames[p]).join(' · ')}</small><small>${g.expires_at ? `到期：${time(g.expires_at)}` : '长期有效'}${g.expires_at && g.expires_at * 1000 <= Date.now() ? ' · 已到期' : ''}</small></div><button class="danger" data-action="revoke" data-id="${g.user_id}/${g.group_id}">撤销</button></div>`).join('') || '<p class="muted">尚未配置授权。新员工默认看不到任何设备。</p>';
  renderAudit();
  renderShares();
}
function renderShares() {
  $('#share-list').innerHTML = data.shares.map(s => `<div class="list-item"><div><b>${esc(s.device_name)} (${esc(s.device_id)})</b><small>${esc(s.grantor_name)} → ${esc(s.recipient_name)} · ${s.active ? '有效' : '已失效'}</small><small>当前权限：${s.effective_permissions.map(p => esc(permissionNames[p] || p)).join(' · ') || '无'} · ${s.expires_at ? `到期：${time(s.expires_at)}` : '长期有效'}</small></div>${s.can_revoke ? `<button class="danger" data-action="revoke-share" data-id="${s.id}">${s.recipient_name === me.name ? '退出分享' : '撤销分享'}</button>` : ''}</div>`).join('') || '<p class="muted">暂无设备分享。在设备目录中选择有权转授的电脑即可分享。</p>';
}
function renderDevices() {
  const search = $('#search').value.toLowerCase(), group = $('#group-filter').value;
  const selectedPath = data.groups.find(g => String(g.id) === group)?.path;
  const rows = data.devices.filter(d => (!group || String(d.group_id) === group || (selectedPath && String(d.device_group_name || groupName(d.group_id)).startsWith(selectedPath + ' / '))) && [d.id, d.name, d.asset_no, d.owner, d.location].some(v => String(v).toLowerCase().includes(search)));
  $('#device-rows').innerHTML = rows.map(d => `<tr><td><b>${esc(d.name)}</b><small>${esc(d.id)} · ${esc(d.platform)}</small></td><td>${esc(d.device_group_name || groupName(d.group_id))}</td><td>${esc(d.asset_no || '—')}<small>${esc(d.owner)}</small></td><td>${esc(d.location || '—')}</td><td><span class="badge ${d.enabled ? '' : 'off'}">${d.enabled ? '可用' : '已停用'}</span><small>${time(d.last_seen)}</small></td><td>${me.is_admin ? `<button class="secondary" data-action="move" data-id="${esc(d.id)}">移动</button><button class="secondary" data-action="toggle-device" data-id="${esc(d.id)}">${d.enabled ? '停用' : '启用'}</button><button class="secondary" data-action="rotate" data-id="${esc(d.id)}">更新凭据</button>` : (d.permissions || []).map(p => esc(permissionNames[p])).join(' · ')}${d.enabled && (me.is_admin || d.can_share) ? `<button class="secondary" data-action="share" data-id="${esc(d.id)}">分享</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6">暂无设备。请登记设备或联系管理员分配权限。</td></tr>';
}
async function openShare(deviceId) {
  const config = await api(`/api/device-shares/options/${encodeURIComponent(deviceId)}`);
  shareDeviceId = deviceId;
  $('#share-form').reset();
  $('#share-error').textContent = '';
  $('#share-device-name').textContent = `${config.name} (${deviceId})`;
  $('#share-permissions').innerHTML = '<legend>允许的操作</legend>' + config.permissions.map(p => `<label class="check"><input name="permissions" value="${esc(p)}" type="checkbox" ${['view', 'connect'].includes(p) ? 'checked' : ''} ${p === 'view' ? 'disabled' : ''}>${esc(permissionNames[p] || p)}</label>`).join('');
  const tomorrow = new Date(Date.now() + 24*60*60*1000);
  const local = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset()*60000);
  $('#share-form').expiry.value = local.toISOString().slice(0, 16);
  $('#share-dialog').showModal();
}
function renderAudit() {
  $('#audit-rows').innerHTML = data.audit.map(e => `<tr><td>${time(e.time)}</td><td>${esc(e.actor)}</td><td>${esc(eventNames[e.action] || e.action)}</td><td>${esc(e.target)}</td><td>${esc(e.detail)}</td></tr>`).join('');
  $('#older-audit').disabled = data.audit.length === 0;
}
function showSecret(result) {
  $('#secret-text').textContent = `设备 ID: ${result.id}\n\n[options]\nenterprise-server = '${location.origin}'\nenterprise-device-token = '${result.device_token}'`;
  $('#secret-dialog').showModal();
}
async function run(task) { try { notice(); await task(); } catch (e) { notice(e.message || String(e), true); } }
function bindForm(id, action) {
  $(id).addEventListener('submit', e => { e.preventDefault(); run(async () => {
    const button = e.target.querySelector('button'); button.disabled = true;
    try { await action(Object.fromEntries(new FormData(e.target)), e.target); } finally { button.disabled = false; }
  }); });
}
bindForm('#login-form', async (body, form) => {
  if (registering && body.password !== body.password_confirmation) throw new Error('两次输入的密码不一致。');
  const created = registering;
  let result;
  $('#toggle-registration').disabled = true;
  try { result = await api(created ? '/api/register' : '/api/login', 'POST', body); }
  finally { $('#toggle-registration').disabled = false; }
  token = result.access_token; me = result.user;
  registrationMode(false); form.display_name.value = '';
  form.password.value = ''; $('#login').hidden = true; $('#workspace').hidden = false;
  $('#identity').textContent = `${me.display_name} · ${me.is_admin ? '管理员' : '员工'}`;
  tab('devices'); await load();
  if (created) notice('注册成功，已自动登录。请联系管理员分配设备权限。');
});
$('#toggle-registration').onclick = () => { notice(); registrationMode(!registering); };
bindForm('#group-form', async (body, form) => { body.parent_id = body.parent_id ? Number(body.parent_id) : null; await api('/api/admin/groups', 'POST', body); form.reset(); await load(); notice('分组已创建。'); });
bindForm('#user-form', async (body, form) => { await api('/api/admin/users', 'POST', body); form.reset(); await load(); notice('账号已创建，请分配设备分组权限。'); });
bindForm('#device-form', async (body, form) => { body.group_id = Number(body.group_id); const result = await api('/api/admin/devices', 'POST', body); form.reset(); await load(); showSecret(result); });
bindForm('#grant-form', async (body, form) => { await api('/api/admin/grants', 'POST', {user_id: Number(body.user_id), group_id: Number(body.group_id), permissions: ['view', ...new FormData(form).getAll('permissions')], expires_at: body.expiry ? Math.floor(new Date(body.expiry).getTime()/1000) : null}); await load(); notice('授权已保存，覆盖该员工在此分组的旧授权。'); });
bindForm('#share-form', async (body, form) => {
  $('#share-error').textContent = ''; $('#cancel-share').disabled = true;
  try {
    await api('/api/device-shares', 'POST', {device_id: shareDeviceId, username: body.username, permissions: ['view', ...new FormData(form).getAll('permissions')], expires_at: body.expiry ? Math.floor(new Date(body.expiry).getTime()/1000) : null});
    $('#share-dialog').close(); await load(); notice('设备已分享。接收者登录后刷新设备目录即可看到。');
  } catch (error) { $('#share-error').textContent = error.message; throw error; }
  finally { $('#cancel-share').disabled = false; }
});
bindForm('#move-form', async body => { const device = data.devices.find(d => d.id === moveId); await api(`/api/admin/devices/${encodeURIComponent(moveId)}`, 'PATCH', {group_id: Number(body.group_id), enabled: Boolean(device.enabled)}); $('#move-dialog').close(); await load(); notice('设备已移动。'); });
bindForm('#password-form', async (body, form) => { await api(`/api/admin/users/${passwordId}/password`, 'POST', body); form.reset(); $('#password-dialog').close(); if (passwordId === me.id) { clearSession(); notice('密码已更新，请重新登录。'); } else { await load(); notice('密码已更新，旧登录会话已注销。'); } });
$('#refresh').onclick = () => run(load);
$('#search').oninput = renderDevices; $('#group-filter').onchange = renderDevices;
$('#logout').onclick = () => run(async () => { try { await api('/api/logout', 'POST', {}); } finally { clearSession(); } });
$('#close-secret').onclick = () => $('#secret-dialog').close();
$('#secret-dialog').addEventListener('close', () => $('#secret-text').textContent = '');
$('#cancel-move').onclick = () => $('#move-dialog').close();
$('#cancel-password').onclick = () => { $('#password-form').reset(); $('#password-dialog').close(); };
$('#cancel-share').onclick = () => $('#share-dialog').close();
$('#older-audit').onclick = () => run(async () => { const rows = await api(`/api/admin/audit?before=${data.audit.at(-1).id}`); data.audit.push(...rows); renderAudit(); if (!rows.length) { $('#older-audit').disabled = true; notice('已加载全部日志。'); } });
document.addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.dataset.tab) { tab(button.dataset.tab); return; }
  const id = button.dataset.id;
  if (!button.dataset.action) return;
  run(async () => {
    switch (button.dataset.action) {
      case 'share': await openShare(id); return;
      case 'revoke-share': if (!confirm('撤销这条分享？其他独立授权仍然有效，已建立的远控会话不会立即断开。')) return; await api(`/api/device-shares/${id}`, 'DELETE'); break;
      case 'delete-group': if (!confirm('删除这个空分组？')) return; await api(`/api/admin/groups/${id}`, 'DELETE'); break;
      case 'toggle-user': { const u = data.users.find(u => u.id === Number(id)); if (!confirm(`${u.status ? '停用' : '启用'} ${u.display_name}？`)) return; await api(`/api/admin/users/${id}`, 'PATCH', {enabled: !u.status}); break; }
      case 'password': passwordId = Number(id); $('#password-dialog').showModal(); return;
      case 'revoke': if (!confirm('撤销此授权？其他父分组或子分组授权仍然有效。')) return; await api(`/api/admin/grants/${id}`, 'DELETE'); break;
      case 'toggle-device': { const d = data.devices.find(d => d.id === id); await api(`/api/admin/devices/${encodeURIComponent(id)}`, 'PATCH', {group_id: d.group_id, enabled: !d.enabled}); break; }
      case 'rotate': if (!confirm('更新后旧设备凭据立即失效，需要在被控端重新配置。继续？')) return; showSecret(await api(`/api/admin/devices/${encodeURIComponent(id)}/rotate-token`, 'POST', {})); break;
      case 'move': moveId = id; $('#move-form').group_id.value = data.devices.find(d => d.id === id).group_id; $('#move-dialog').showModal(); return;
    }
    await load(); notice('操作已保存。');
  });
});
