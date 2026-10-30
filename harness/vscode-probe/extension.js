// Test-only extension: lists language models VS Code exposes and sends one prompt to each BYOK ("customendpoint") model.
const vscode = require('vscode');
const fs = require('fs');
const OUT = process.env.LMTEST_OUT;
const w = (o) => fs.appendFileSync(OUT, JSON.stringify({ t: Date.now(), ...o }) + '\n');

exports.activate = async () => {
  try {
    w({ step: 'activated', version: vscode.version });
    await new Promise((r) => setTimeout(r, Number(process.env.LMTEST_WAIT_MS || 8000)));
    const all = await vscode.lm.selectChatModels({});
    w({ step: 'list', models: all.map((m) => ({ id: m.id, vendor: m.vendor, family: m.family, name: m.name, maxInputTokens: m.maxInputTokens })) });
    const vendor = process.env.LMTEST_VENDOR || 'customendpoint';
    for (const m of all.filter((x) => x.vendor === vendor)) {
      try {
        const cts = new vscode.CancellationTokenSource();
        const resp = await m.sendRequest([vscode.LanguageModelChatMessage.User('Reply with the single word: ok')], {}, cts.token);
        let text = '';
        for await (const c of resp.text) text += c;
        w({ step: 'send-ok', model: m.id, text });
      } catch (e) {
        w({ step: 'send-error', model: m.id, error: String(e && e.message || e), code: e && e.code });
      }
    }
  } catch (e) {
    w({ step: 'fatal', error: String(e && e.stack || e) });
  }
  w({ step: 'done' });
  if (process.env.LMTEST_QUIT !== '0') vscode.commands.executeCommand('workbench.action.quit');
};
