import fs from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const root = path.join(repoRoot, 'data', 'sunairport');
const healthPath = path.join(root, 'health.json');
const latestPath = path.join(root, 'latest.json');
const stage = process.argv[2] || 'UNKNOWN';
const state = stage === 'NORMALIZE' ? 'QA_FAILED' : 'FAILED';

let previousLatest = null;
try { previousLatest = JSON.parse(await fs.readFile(latestPath, 'utf8')); } catch {}
await fs.mkdir(root, { recursive: true });

const health = {
  module: 'Sun Airport flights',
  state,
  scheduler_triggered: true,
  job_started: true,
  collector_completed: stage !== 'COLLECT',
  parser_passed: false,
  normalization_passed: false,
  qa_passed: false,
  commit_succeeded: null,
  collected_at_vn: new Date().toISOString(),
  source_date: null,
  retry_count: Number(process.env.SUNAIRPORT_RETRY_COUNT || 0),
  last_successful_run: previousLatest?.collected_at_vn || null,
  fallback_used: false,
  failed_stage: stage,
  run_id: process.env.GITHUB_RUN_ID || null,
  evidence_class: 'DIRECT',
  root_cause: 'NGUYÊN NHÂN CHƯA XÁC ĐỊNH - xem log/artifact'
};
await fs.writeFile(healthPath, JSON.stringify(health, null, 2) + '\n');
console.log(JSON.stringify(health));
