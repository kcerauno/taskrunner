const vscode = require("vscode");
const { execFile } = require("child_process");
const path = require("path");

const SECTION_RE = /^###\s+(RB-(?:CMD|EXPECTED|DESCRIPTION|LOCALDEF|ONFAIL))\s*$/i;
const HEADING_RE = /^##\s+(?!#)(.+?)\s*$/;
const FENCE_RE = /^\s*```/;

/** runbook 手順書らしさの判定。markdown なら何でも check にかけると誤診断が出るため。 */
function isRunbookDoc(document) {
  if (document.languageId !== "markdown") return false;
  const text = document.getText();
  return /^###\s+RB-/im.test(text) || /^\s*```runbook\s*$/im.test(text);
}

/** ```runbook / ```bash などのフェンス外だけを対象に構造を取る。 */
function scanStructure(document) {
  const steps = [];
  let inFence = false;
  for (let i = 0; i < document.lineCount; i++) {
    const line = document.lineAt(i).text;
    if (FENCE_RE.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const h = HEADING_RE.exec(line);
    if (h) {
      steps.push({ line: i, title: h[1], sections: [] });
      continue;
    }
    const s = SECTION_RE.exec(line);
    if (s && steps.length) {
      steps[steps.length - 1].sections.push({ line: i, name: s[1].toUpperCase() });
    }
  }
  return steps;
}

function resolveExecutable(document) {
  const config = vscode.workspace.getConfiguration("runbook", document ? document.uri : null);
  let exe = config.get("executablePath") || "runbook";
  const folder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : undefined;
  const root = folder ? folder.uri.fsPath : (vscode.workspace.workspaceFolders || [{ uri: { fsPath: "" } }])[0].uri.fsPath;
  exe = exe.replace(/\$\{workspaceFolder\}/g, root);
  return { exe, cwd: root || path.dirname(document ? document.uri.fsPath : ".") };
}

/**
 * 診断の行を絞り込む。CLI が返すのはステップ見出しの行なので、
 * メッセージが特定セクション(RB-ONFAIL など)を指しているときは
 * そのセクション見出しの行へ寄せる。
 */
function refineRange(document, diag, steps) {
  const lineNo = (diag.line || 1) - 1;
  const clamped = Math.max(0, Math.min(lineNo, document.lineCount - 1));
  let target = clamped;
  const m = /RB-[A-Z]+/i.exec(diag.message || "");
  if (m && diag.step != null) {
    const step = steps.find((s) => s.line === clamped);
    if (step) {
      const sec = step.sections.find((x) => x.name === m[0].toUpperCase());
      if (sec) target = sec.line;
    }
  }
  const text = document.lineAt(target).text;
  const start = text.length - text.trimStart().length;
  return new vscode.Range(target, start, target, Math.max(text.length, start + 1));
}

function runCheckJson(document) {
  const { exe, cwd } = resolveExecutable(document);
  return new Promise((resolve) => {
    execFile(
      exe,
      ["check", "--json", document.uri.fsPath],
      { cwd, timeout: 20000, maxBuffer: 4 * 1024 * 1024 },
      (error, stdout, stderr) => {
        const out = (stdout || "").trim();
        if (out) {
          try {
            resolve({ payload: JSON.parse(out.split("\n").pop()) });
            return;
          } catch (e) {
            /* JSON でなければ下の失敗扱いへ */
          }
        }
        resolve({ error: (stderr || "").trim() || (error && error.message) || "runbook check の出力を解釈できません" });
      }
    );
  });
}

let diagnostics;
let output;
let checkFailureReported = false;

async function updateDiagnostics(document) {
  if (!diagnostics) return;
  const config = vscode.workspace.getConfiguration("runbook", document.uri);
  if (!config.get("diagnosticsEnabled") || !isRunbookDoc(document) || document.isUntitled) {
    diagnostics.delete(document.uri);
    return;
  }
  const result = await runCheckJson(document);
  if (result.error) {
    diagnostics.delete(document.uri);
    output.appendLine(`[check] ${document.uri.fsPath}: ${result.error}`);
    if (!checkFailureReported) {
      checkFailureReported = true;
      vscode.window.showWarningMessage(
        "runbook コマンドを実行できませんでした。設定 runbook.executablePath を確認してください(例: ${workspaceFolder}/.venv/bin/runbook)。"
      );
    }
    return;
  }
  checkFailureReported = false;
  const steps = scanStructure(document);
  const items = (result.payload.diagnostics || []).map((d) => {
    const severity =
      d.severity === "error" ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
    const diag = new vscode.Diagnostic(refineRange(document, d, steps), d.message, severity);
    diag.source = "runbook check";
    return diag;
  });
  diagnostics.set(document.uri, items);
}

class RunbookSymbolProvider {
  provideDocumentSymbols(document) {
    if (!isRunbookDoc(document)) return [];
    const steps = scanStructure(document);
    return steps.map((step, index) => {
      const end = index + 1 < steps.length ? steps[index + 1].line - 1 : document.lineCount - 1;
      const range = new vscode.Range(step.line, 0, Math.max(end, step.line), 0);
      const selection = document.lineAt(step.line).range;
      const isManual = !step.sections.some((s) => s.name === "RB-CMD");
      const symbol = new vscode.DocumentSymbol(
        step.title,
        isManual ? "手動ステップ" : "",
        isManual ? vscode.SymbolKind.Interface : vscode.SymbolKind.Function,
        range,
        selection
      );
      symbol.children = step.sections.map(
        (sec) =>
          new vscode.DocumentSymbol(
            sec.name,
            "",
            vscode.SymbolKind.Field,
            document.lineAt(sec.line).range,
            document.lineAt(sec.line).range
          )
      );
      return symbol;
    });
  }
}

function runInTerminal(args, { save }) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "markdown") {
    vscode.window.showWarningMessage("手順書の Markdown ファイルを開いた状態で実行してください。");
    return Promise.resolve();
  }
  const document = editor.document;
  const done = save ? document.save() : Promise.resolve(true);
  return Promise.resolve(done).then(() => {
    const { exe, cwd } = resolveExecutable(document);
    const terminal =
      vscode.window.terminals.find((t) => t.name === "runbook") ||
      vscode.window.createTerminal({ name: "runbook", cwd });
    terminal.show();
    const quote = (s) => (/[\s'"$]/.test(s) ? `'${s.replace(/'/g, "'\\''")}'` : s);
    terminal.sendText([exe, ...args, document.uri.fsPath].map(quote).join(" "));
  });
}

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection("runbook");
  output = vscode.window.createOutputChannel("runbook");
  context.subscriptions.push(diagnostics, output);

  context.subscriptions.push(
    vscode.languages.registerDocumentSymbolProvider(
      { language: "markdown" },
      new RunbookSymbolProvider()
    )
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (vscode.workspace.getConfiguration("runbook", document.uri).get("checkOnSave")) {
        updateDiagnostics(document);
      }
    }),
    vscode.workspace.onDidOpenTextDocument((document) => updateDiagnostics(document)),
    vscode.workspace.onDidCloseTextDocument((document) => diagnostics.delete(document.uri))
  );
  vscode.workspace.textDocuments.forEach((document) => updateDiagnostics(document));

  context.subscriptions.push(
    vscode.commands.registerCommand("runbook.check", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      await editor.document.save();
      await updateDiagnostics(editor.document);
      const found = diagnostics.get(editor.document.uri) || [];
      vscode.window.showInformationMessage(
        found.length ? `runbook check: 指摘 ${found.length} 件(問題パネルを参照)` : "runbook check: 問題ありません"
      );
    }),
    vscode.commands.registerCommand("runbook.checkPreview", () =>
      runInTerminal(["check", "--preview"], { save: true })
    ),
    vscode.commands.registerCommand("runbook.list", () => runInTerminal(["list", "--detail"], { save: true })),
    vscode.commands.registerCommand("runbook.renumber", () => runInTerminal(["renumber"], { save: true })),
    vscode.commands.registerCommand("runbook.run", () => runInTerminal(["run", "-i"], { save: true }))
  );
}

function deactivate() {}

// scanStructure / isRunbookDoc / RunbookSymbolProvider / refineRange はテスト用に公開する
module.exports = {
  activate,
  deactivate,
  scanStructure,
  isRunbookDoc,
  refineRange,
  RunbookSymbolProvider,
};
