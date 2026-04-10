const state = {
  session: null,
  practices: [],
  members: [],
  loading: true,
  error: '',
};

function h(strings, ...vals) {
  return strings.reduce((acc, str, i) => acc + str + (vals[i] ?? ''), '');
}

function formatDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  if (Number.isNaN(date.getTime())) return dateStr;
  const weeks = ['日', '月', '火', '水', '木', '金', '土'];
  return `${date.getMonth() + 1}/${date.getDate()}(${weeks[date.getDay()]})`;
}

async function api(path, method='GET', body=null) {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body ? {'Content-Type':'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'api_error');
  return data;
}

async function bootstrap() {
  try {
    const session = await api('/api/session');
    state.session = session.logged_in ? session : null;
    if (state.session) {
      const payload = await api('/api/practices');
      state.practices = payload.practices;
      state.members = payload.members;
    }
  } catch (e) {
    state.error = '初期表示に失敗しました。';
  } finally {
    state.loading = false;
    render();
  }
}

async function refreshPractices() {
  const payload = await api('/api/practices');
  state.practices = payload.practices;
  state.members = payload.members;
  render();
}

function countSummary(practice) {
  const values = Object.values(practice.attendance || {});
  const yes = values.filter(v => v === true).length;
  const no = values.filter(v => v === false).length;
  const pending = values.filter(v => v === null).length;
  return { yes, no, pending };
}

function shell(content) {
  return h`<div class="shell">${content}<div class="footer-note">ブラウザ専用 / インストール不要 / PINログイン対応</div></div>`;
}

function homeView() {
  const session = state.session;
  if (!session) return loginView();
  if (session.role === 'admin') return adminView();
  return memberView();
}

function loginView() {
  const memberOptions = ['<option value="">選手を選択してください</option>']
    .concat(['大池音々','森田健友','美馬碧仁','荻原瑛史','尾山旭','笠原現'].map(name => `<option value="${name}">${name}</option>`))
    .join('');
  return shell(h`
    <div class="topbar">
      <div>
        <div class="brand">練習出欠アプリ</div>
        <div class="sub">管理者用ページ / 登録者用ページ</div>
      </div>
    </div>
    <div class="grid">
      <div class="card stack">
        <h2>管理者ログイン</h2>
        <div class="field">
          <label class="label">管理者PIN</label>
          <input id="admin-pin" inputmode="numeric" placeholder="6桁PIN">
        </div>
        <button class="primary" id="admin-login-btn">管理者として入る</button>
      </div>
      <div class="card stack">
        <h2>登録者ログイン</h2>
        <div class="field">
          <label class="label">名前</label>
          <select id="member-name">${memberOptions}</select>
        </div>
        <div class="field">
          <label class="label">個人PIN</label>
          <input id="member-pin" inputmode="numeric" placeholder="6桁PIN">
        </div>
        <button class="primary" id="member-login-btn">登録者として入る</button>
      </div>
      <div class="notice">このアプリはブラウザで使うシンプルな出欠管理アプリです。</div>
      ${state.error ? `<div class="error center">${state.error}</div>` : ''}
    </div>
  `);
}

function adminView() {
  const cards = state.practices.map(practice => {
    const s = countSummary(practice);
    const memberRows = state.members.map(member => {
      const status = practice.attendance[member];
      const clsY = status === true ? 'choice active-ok' : 'choice';
      const clsN = status === false ? 'choice active-ng' : 'choice';
      const clsP = status === null ? 'choice active-pending' : 'choice';
      return h`<div class="memberrow">
        <div class="membername">${member}</div>
        <div class="switches">
          <button class="${clsY}" data-action="admin-status" data-id="${practice.id}" data-member="${member}" data-status="yes">出席</button>
          <button class="${clsN}" data-action="admin-status" data-id="${practice.id}" data-member="${member}" data-status="no">欠席</button>
          <button class="${clsP}" data-action="admin-status" data-id="${practice.id}" data-member="${member}" data-status="pending">未</button>
        </div>
      </div>`;
    }).join('');
    return h`<div class="card practice-card">
      <div class="practice-head">
        <div>
          <div class="practice-date">${formatDate(practice.date)}</div>
          <div class="summary">登録日 ${practice.date}</div>
        </div>
        <div class="time-badge">${practice.time}</div>
      </div>
      <div class="meta3">
        <span>出席 ${s.yes}</span>
        <span>欠席 ${s.no}</span>
        <span>未回答 ${s.pending}</span>
      </div>
      <div class="stack">${memberRows}</div>
      <button class="smallbtn danger" data-action="delete-practice" data-id="${practice.id}">この練習を削除</button>
    </div>`;
  }).join('');

  return shell(h`
    <div class="topbar">
      <div>
        <div class="brand">管理者用ページ</div>
        <div class="sub">練習日と練習時間を登録 / 出欠状況を確認</div>
      </div>
      <button class="ghost" id="logout-btn">ログアウト</button>
    </div>
    <div class="grid">
      <div class="card stack">
        <h2>練習を登録</h2>
        <div class="field">
          <label class="label">練習日</label>
          <input type="date" id="new-date">
        </div>
        <div class="field">
          <label class="label">練習時間</label>
          <input id="new-time" placeholder="例 18:00-19:30">
        </div>
        <button class="primary" id="add-practice-btn">登録する</button>
      </div>
      ${cards || '<div class="card center">登録されている練習はありません。</div>'}
    </div>
  `);
}

function memberView() {
  const member = state.session.member;
  const cards = state.practices.map(practice => {
    const status = practice.attendance[member];
    const clsY = status === true ? 'choice active-ok' : 'choice';
    const clsN = status === false ? 'choice active-ng' : 'choice';
    const clsP = status === null ? 'choice active-pending' : 'choice';
    return h`<div class="card practice-card">
      <div class="practice-head">
        <div>
          <div class="practice-date">${formatDate(practice.date)}</div>
          <div class="summary">${member}さんの回答</div>
        </div>
        <div class="time-badge">${practice.time}</div>
      </div>
      <div class="pillrow">
        <button class="${clsY}" data-action="member-status" data-id="${practice.id}" data-status="yes">出席</button>
        <button class="${clsN}" data-action="member-status" data-id="${practice.id}" data-status="no">欠席</button>
        <button class="${clsP}" data-action="member-status" data-id="${practice.id}" data-status="pending">未回答</button>
      </div>
    </div>`;
  }).join('');
  return shell(h`
    <div class="topbar">
      <div>
        <div class="brand">${member}</div>
        <div class="sub">自分の出欠だけ回答できます</div>
      </div>
      <button class="ghost" id="logout-btn">ログアウト</button>
    </div>
    <div class="grid">${cards || '<div class="card center">練習が登録されていません。</div>'}</div>
  `);
}

function render() {
  const app = document.getElementById('app');
  if (state.loading) {
    app.innerHTML = shell('<div class="card center">読み込み中...</div>');
    return;
  }
  app.innerHTML = homeView();
  bindEvents();
}

function bindEvents() {
  const adminBtn = document.getElementById('admin-login-btn');
  if (adminBtn) adminBtn.onclick = async () => {
    try {
      await api('/api/login', 'POST', { mode: 'admin', pin: document.getElementById('admin-pin').value });
      state.session = await api('/api/session');
      await refreshPractices();
    } catch {
      alert('管理者PINが正しくありません。連続で失敗すると一時的に制限されます。');
    }
  };

  const memberBtn = document.getElementById('member-login-btn');
  if (memberBtn) memberBtn.onclick = async () => {
    try {
      await api('/api/login', 'POST', {
        mode: 'member',
        member: document.getElementById('member-name').value,
        pin: document.getElementById('member-pin').value,
      });
      state.session = await api('/api/session');
      await refreshPractices();
    } catch {
      alert('名前またはPINが正しくありません。連続で失敗すると一時的に制限されます。');
    }
  };

  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) logoutBtn.onclick = async () => {
    await api('/api/logout', 'POST', {});
    state.session = null;
    render();
  };

  const addBtn = document.getElementById('add-practice-btn');
  if (addBtn) addBtn.onclick = async () => {
    const date = document.getElementById('new-date').value;
    const time = document.getElementById('new-time').value.trim();
    if (!date || !time) return alert('練習日と練習時間を入力してください。');
    await api('/api/practices/add', 'POST', { date, time });
    await refreshPractices();
    document.getElementById('new-date').value = '';
    document.getElementById('new-time').value = '';
  };

  document.querySelectorAll('[data-action="delete-practice"]').forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('この練習を削除しますか？')) return;
      await api('/api/practices/delete', 'POST', { id: Number(btn.dataset.id) });
      await refreshPractices();
    };
  });

  document.querySelectorAll('[data-action="member-status"]').forEach(btn => {
    btn.onclick = async () => {
      const status = btn.dataset.status === 'yes' ? true : btn.dataset.status === 'no' ? false : null;
      await api('/api/attendance/update', 'POST', {
        id: Number(btn.dataset.id),
        member: state.session.member,
        status,
      });
      await refreshPractices();
    };
  });

  document.querySelectorAll('[data-action="admin-status"]').forEach(btn => {
    btn.onclick = async () => {
      const status = btn.dataset.status === 'yes' ? true : btn.dataset.status === 'no' ? false : null;
      await api('/api/attendance/update', 'POST', {
        id: Number(btn.dataset.id),
        member: btn.dataset.member,
        status,
      });
      await refreshPractices();
    };
  });
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}

bootstrap();
