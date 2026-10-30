// Generic Playwright driver for the pinned VS Code. Config comes from a JSON file passed as argv[2]:
// { scenario, modelsJson?, settings?, probe?: bool, extDir?, wait_ms?, steps?: [...], screenshot?: true }
// steps: {do:'wait',ms} | {do:'command',id} | {do:'palette',text} | {do:'type',text} | {do:'press',key}
//        | {do:'shot',name} | {do:'frames'} | {do:'click_text',text} | {do:'webview_type',text,submit}
const { _electron: electron } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const CODE = path.join(__dirname, '.vscode-test', 'vscode-win32-x64-archive-1.142.0', 'Code.exe');
const base = path.join(ROOT, 'work', 'vscode', cfg.scenario);
if (!cfg.keepProfile) fs.rmSync(base, { recursive: true, force: true });
const user = path.join(base, 'user-data', 'User');
fs.mkdirSync(user, { recursive: true });
const ws = path.join(base, 'ws');
fs.mkdirSync(ws, { recursive: true });
if (cfg.modelsJson && !cfg.keepProfile) fs.copyFileSync(path.resolve(cfg.modelsJson), path.join(user, 'chatLanguageModels.json'));
const settings = Object.assign({
  'security.workspace.trust.enabled': false, 'telemetry.telemetryLevel': 'off', 'update.mode': 'none',
  'workbench.startupEditor': 'none', 'chat.agentHost.byokModels.enabled': true,
}, cfg.settings || {});
fs.writeFileSync(path.join(user, 'settings.json'), JSON.stringify(settings, null, 2));
const out = path.join(base, 'probe.jsonl');

const env = {};
for (const [k, v] of Object.entries(process.env)) {
  if (/^(CLAUDE_CODE_|ANTHROPIC_|CLAUDECODE|OPENAI_|CODEX_|ELECTRON_RUN_AS_NODE)/.test(k) || k === 'CLAUDE_CONFIG_DIR') continue;
  env[k] = v;
}
env.PATH = (cfg.pathPrepend ? cfg.pathPrepend + ';' : '') + env.PATH;
Object.assign(env, { LMTEST_QUIT: '0' }, cfg.env || {}, { LMTEST_OUT: out });

const log = (o) => console.log(JSON.stringify(o));
(async () => {
  const args = ['--user-data-dir', path.join(base, 'user-data'), '--extensions-dir', path.resolve(cfg.extDir || path.join(ROOT, 'vscode-ext')),
    '--new-window', '--disable-workspace-trust', '--disable-updates', '--skip-welcome', '--skip-release-notes'];
  if (cfg.probe !== false) args.push('--extensionDevelopmentPath', path.join(ROOT, 'vscode-probe'));
  for (const a of cfg.args || []) args.push(a.replace('{base}', base));
  args.push(ws);
  const app = await electron.launch({ executablePath: CODE, args, env, timeout: 60000 });
  let page = await app.firstWindow();
  for (let i = 0; i < 30; i++) {
    const w = app.windows().find((x) => !x.isClosed() && /workbench\.html/.test(x.url()));
    if (w) { page = w; break; }
    await new Promise((r) => setTimeout(r, 1000));
  }
  log({ window: page.url().slice(0, 120) });
  const shot = async (name) => { const p = path.join(base, `${name}.png`); await page.screenshot({ path: p }); log({ shot: p }); };
  await page.waitForTimeout(cfg.wait_ms || 15000);
  for (const s of cfg.steps || []) {
    try {
      if (s.do === 'wait') await page.waitForTimeout(s.ms);
      else if (s.do === 'shot') await shot(s.name);
      else if (s.do === 'palette') { await page.keyboard.press('F1'); await page.waitForTimeout(500); await page.keyboard.type(s.text); await page.waitForTimeout(800); await page.keyboard.press('Enter'); }
      else if (s.do === 'type') await page.keyboard.type(s.text, { delay: 15 });
      else if (s.do === 'click_xy') await page.mouse.click(s.x, s.y);
      else if (s.do === 'press') await page.keyboard.press(s.key);
      else if (s.do === 'frames') log({ frames: page.frames().map((f) => ({ url: f.url().slice(0, 140), name: f.name() })) });
      else if (s.do === 'click_text') { await page.getByText(s.text, { exact: false }).first().click({ timeout: 8000 }); }
      else if (s.do === 'webview_type') {
        let target = null;
        for (const f of page.frames()) { try { if (await f.locator(s.selector || '[contenteditable="true"], textarea').count()) { target = f; } } catch (e) {} }
        if (!target) throw new Error('no frame with input');
        const loc = target.locator(s.selector || '[contenteditable="true"], textarea').first();
        await loc.click(); await page.keyboard.type(s.text, { delay: 10 });
        if (s.submit !== false) await page.keyboard.press('Enter');
        log({ typed_in_frame: target.url().slice(0, 100) });
      } else if (s.do === 'text') {
        const t = await page.evaluate(() => document.body.innerText.slice(0, 1500)); log({ text: t });
      } else if (s.do === 'webview_text') {
        const parts = [];
        for (const f of page.frames()) { try { const t = await f.evaluate(() => document.body && document.body.innerText); if (t && t.trim()) parts.push({ url: f.url().slice(0, 80), text: t.slice(0, 800) }); } catch (e) {} }
        log({ webview_text: parts });
      }
      log({ step: s.do, ok: true, arg: s.id || s.text || s.name || s.ms });
    } catch (e) { log({ step: s.do, ok: false, error: String(e.message || e).slice(0, 300) }); }
  }
  await shot('final');
  const pid = app.process().pid;
  await Promise.race([app.close().catch(() => {}), new Promise((r) => setTimeout(r, 8000))]);
  try { process.kill(pid); } catch (e) {}
  log({ done: true });
  process.exit(0);
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
