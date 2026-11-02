import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const WORKSPACES = path.resolve(HERE, '../..');
const DEFAULT_JOBS = path.join(ROOT, 'data', 'jobs.csv');
const CONTACT_SCRIPT = process.env.BROWSER_OPS_CONTACT ||
  path.join(WORKSPACES, 'browser-ops', 'extensions', 'boss', 'contact.mjs');
const STATUS_SCRIPT = path.join(HERE, 'set_status.py');
const PYTHON = process.env.PYTHON || 'python3';

function parseCsv(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function readJobs(file) {
  const text = fs.readFileSync(file, 'utf8').replace(/^﻿/, '');
  const table = parseCsv(text);
  const header = table[0];
  const rows = table.slice(1).map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ''])));
  return { header, rows };
}

function parseContactOutput(stdout) {
  const text = String(stdout || '').trim();
  if (!text) return null;
  const start = text.indexOf('{');
  if (start < 0) return null;
  return JSON.parse(text.slice(start));
}

function markApplied(report, jobId, jobsFile) {
  const isNewlyApplied = !report.error && report.clicked && report.sent;
  const alreadyContacted = report.error === 'already_contacted';
  if (!isNewlyApplied && !alreadyContacted) return;
  try {
    const proc = spawnSync(PYTHON, [
      STATUS_SCRIPT,
      '--job-id', jobId,
      '--status', '已投递',
      '--jobs-csv', jobsFile,
    ], { encoding: 'utf8', timeout: 30000, maxBuffer: 1024 * 1024 });
    let result = null;
    try {
      result = parseContactOutput(proc.stdout);
    } catch (error) {
      result = null;
    }
    if (proc.error) throw proc.error;
    if (!result || result.error) {
      throw new Error((proc.stderr || '').trim().slice(0, 300) ||
        `状态写入未返回结果（exit ${proc.status}）`);
    }
    report.status_before = Array.isArray(result.old_status)
      ? (result.old_status[0] ?? '')
      : String(result.old_status ?? '');
    report.status_after = result.new_status || report.status_after;
    report.status_updated = true;
  } catch (error) {
    report.status_error = error.message;
  }
}

const { values } = parseArgs({
  options: {
    'job-id': { type: 'string' },
    'jobs-csv': { type: 'string' },
    confirm: { type: 'boolean', default: false },
    'allow-empty-analysis': { type: 'boolean', default: false },
  },
});

const jobId = values['job-id'];
if (!jobId) {
  console.log(JSON.stringify({ error: '需要 --job-id' }, null, 2));
  process.exit(2);
}
if (!values.confirm) {
  console.log(JSON.stringify({ error: '这是真实发送动作，必须显式加 --confirm 才会点击“立即沟通”', job_id: jobId }, null, 2));
  process.exit(2);
}

const jobsFile = values['jobs-csv'] || DEFAULT_JOBS;
const { rows } = readJobs(jobsFile);
const job = rows.find(r => (r.job_id || '').trim() === jobId.trim());
if (!job) {
  console.log(JSON.stringify({ error: `找不到 job_id：${jobId}`, jobs_csv: jobsFile }, null, 2));
  process.exit(2);
}
const analysis = (job.analysis || '').trim();
if (!analysis && !values['allow-empty-analysis']) {
  console.log(JSON.stringify({ error: '该岗位 analysis 为空；请先用 skill 分析并写入 analysis，或显式加 --allow-empty-analysis', job_id: jobId }, null, 2));
  process.exit(2);
}
if (!/^https?:\/\//.test(job.url || '')) {
  console.log(JSON.stringify({ error: '岗位 URL 不合法', job_id: jobId, url: job.url }, null, 2));
  process.exit(2);
}
if (!fs.existsSync(CONTACT_SCRIPT)) {
  console.log(JSON.stringify({ error: `找不到 browser-ops 沟通动作：${CONTACT_SCRIPT}` }, null, 2));
  process.exit(2);
}

const report = {
  job_id: jobId,
  title: job.title,
  company: job.company,
  url: job.url,
  analysis,
  started_at: new Date().toISOString(),
  clicked: false,
  sent: false,
  button_before: '',
  button_after: '',
  chat_target: null,
  chat_top: [],
  error: '',
  status_before: job.status || '',
  status_after: job.status || '',
  status_updated: false,
  status_error: '',
  contact_script: CONTACT_SCRIPT,
};

try {
  const proc = spawnSync(process.execPath, [
    CONTACT_SCRIPT,
    '--url', job.url,
    '--company', job.company || '',
    '--confirm',
  ], { encoding: 'utf8', timeout: 120000, maxBuffer: 10 * 1024 * 1024 });

  if (proc.error) throw proc.error;
  let contact = null;
  try {
    contact = parseContactOutput(proc.stdout);
  } catch (error) {
    throw new Error(`沟通动作返回无法解析：${error.message}\nstdout: ${(proc.stdout || '').slice(0, 500)}\nstderr: ${(proc.stderr || '').slice(0, 500)}`);
  }
  if (!contact) {
    throw new Error(`沟通动作没有返回结果（exit ${proc.status}）\nstdout: ${(proc.stdout || '').slice(0, 500)}\nstderr: ${(proc.stderr || '').slice(0, 500)}`);
  }

  report.started_at = contact.started_at || report.started_at;
  report.clicked = Boolean(contact.clicked);
  report.sent = Boolean(contact.sent);
  report.button_before = contact.button_before || '';
  report.button_after = contact.button_after || '';
  report.chat_target = contact.chat_target || null;
  report.chat_top = contact.chat_top || [];
  report.chat_error = contact.chat_error || '';
  report.error = contact.error || '';
  if (proc.status !== 0 && !report.error) {
    report.error = `沟通动作退出码 ${proc.status}: ${(proc.stderr || '').trim().slice(0, 300)}`;
  }
  if (report.error === 'already_contacted') process.exitCode = 0;
  else if (proc.status !== 0) process.exitCode = 1;
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  markApplied(report, jobId, jobsFile);
  report.finished_at = new Date().toISOString();
  console.log(JSON.stringify({ report }, null, 2));
}
