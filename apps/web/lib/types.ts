// Shapes returned by services/api (see services/api/schemas.py and the route modules).

export type Health = { status: string; db: string };

export type Project = { id: string; title: string; description: string | null; created_at: string };

export type Stage = {
  name: string;
  status: string;
  attempts: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type Asset = {
  id: string;
  project_id: string;
  kind: "source" | "reference";
  status: "uploaded" | "queued" | "processing" | "ready" | "failed";
  original_filename: string;
  size_bytes: number;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  has_audio: boolean | null;
  language: string | null;
  last_error: string | null;
  created_at: string;
  stages?: Stage[];
};

export type ProjectDetail = Project & { assets: Asset[] };

export type Render = { id: string; status: "done" | "failed"; duration: number | null; error: string | null; created_at: string };

export type Version = { version: number; content_hash: string; created_by: string; created_at: string; renders: Render[] };

export type Action = {
  step: number;
  name: string;
  args: Record<string, unknown>;
  source: string;
  ok: boolean;
  error: string | null;
  version_before: number | null;
  version_after: number | null;
  stage: string | null;
};

export type Edit = {
  id: string;
  project_id: string;
  instructions: string;
  status: "queued" | "running" | "rendered" | "failed";
  reference_asset_id: string | null;
  constraints: { min_duration: number; max_duration: number } | null;
  agent_version: string | null;
  error: string | null;
  trace_id: string | null;
  created_at: string;
};

export type EditDetail = Edit & {
  source_asset_ids: string[];
  context_tags: string[] | null;
  memory_used: { statement?: string; confidence?: number }[] | null;
  agent_config: Record<string, unknown> | null;
  plan: Record<string, unknown> | null;
  versions: Version[];
  actions: Action[];
};

export type Clip = {
  asset_id: string;
  src_in: number;
  src_out: number;
  transition_in: string;
  transition_duration: number;
  crop_x: number;
  purpose: string | null;
};

export type Timeline = {
  output: { width: number; height: number; min_duration: number; max_duration: number };
  assets: { id: string; duration: number }[];
  video: Clip[];
  captions: { start: number; end: number; text: string }[];
  titles: { start: number; end: number; text: string }[];
  style: { color: string; captions: { position: string } };
  captions_source: string;
};

export type Evidence = { start: number | null; end: number | null; detail: string };

export type Check = {
  id: string;
  kind: "deterministic" | "signal" | "model";
  category: string;
  severity: string;
  passed: boolean | null;
  score: number | null;
  message: string;
  explanation: string | null;
  evidence: Evidence[];
  measurements: Record<string, unknown>;
};

export type Category = { rate: number; passed: number; total: number };

export type EvaluationSummary = {
  id: string;
  render_id: string;
  version: number;
  evaluator_version: string;
  judge_model: string | null;
  technical_gate_passed: boolean;
  pass_rate: number;
  by_category: Record<string, Category>;
  failed: string[];
  trace_id: string | null;
  created_at: string;
};

export type Evaluation = EvaluationSummary & { report: { checks: Check[]; seconds?: number } };

export type MemoryResult = {
  status: "done" | "awaiting_confirmation";
  thread_id: string;
  questions?: { preference_id: string; question: string }[];
  [k: string]: unknown;
};

export type Preference = {
  id: string;
  category: string;
  attribute: string;
  value: string;
  statement: string;
  context: string[];
  source: string;
  status: string;
  confidence: number;
  support_count: number;
  contradict_count: number;
  last_seen_at: string | null;
  confirmed_at: string | null;
  evidence: unknown[];
};

export type Confirmation = { thread_id: string; preference_id: string; question: string; created_at: string };

export type AgentVersion = {
  version: string;
  status: string;
  parent: string | null;
  origin: string;
  rationale: string | null;
  config: Record<string, unknown>;
  created_at: string;
};

export type Promotion = { from: string; to: string; approved_by: string; note: string | null; experiment_id: string; at: string };

export type Cluster = {
  id: string;
  analysis_id: string;
  agent_version: string;
  method: string;
  label: string;
  check_id: string | null;
  severity: string;
  size: number;
  rate: number;
  tasks: string[];
  examples: { task: string; message: string; explanation?: string; evidence?: Evidence[] }[] | null;
  diagnosis: {
    summary?: string;
    root_causes?: { cause: string; evidence: string[]; confidence: string }[];
    probes?: Record<string, unknown>;
  } | null;
};

export type Delta = { baseline: number | null; candidate: number | null; delta: number | null; n?: number };

export type Paired = {
  mean_diff: number;
  ci95: [number, number];
  wins: number;
  losses: number;
  ties: number;
  per_task: Record<string, number>;
};

export type Comparison = {
  tasks: number;
  metrics: Record<string, Delta>;
  checks: Record<string, Delta>;
  paired: Paired;
  by_split?: Record<string, Delta>;
  after_rerun?: Record<string, Delta>;
  newly_failed: string[];
  newly_rendered: string[];
  flaky?: string[];
  scope?: {
    name: string;
    tasks?: number;
    task_ids?: string[];
    checks: Record<string, Delta>;
    metrics?: Record<string, Delta>;
    paired?: Paired;
    newly_failed?: string[];
  };
  control?: { task_ids?: string[]; checks: Record<string, { n: number; flips: number }> };
};

export type Gates = {
  eligible: boolean;
  scope?: string | null;
  critical: string[];
  regressions: string[];
  improvements: string[];
  notes: string[];
  advisory_checks?: string[];
  thresholds: Record<string, number>;
};

export type ExperimentRow = {
  id: string;
  name: string;
  status: string;
  baseline_version: string;
  candidate_version: string;
  change: {
    hypothesis?: string;
    targets?: string[];
    policy_changes?: Record<string, unknown>;
    expected_effect?: string;
    risks?: string;
    origin?: string;
    submitted_by?: string;
    planner_addendum?: string;
    repair_addendum?: string;
  } | null;
  thread_id: string | null;
  eligible: boolean | null;
  created_at: string;
  decision_by: string | null;
  decided_at: string | null;
};

export type Experiment = ExperimentRow & {
  dataset_version: string;
  evaluator_version: string;
  models: Record<string, string>;
  splits: string[];
  n_runs: number;
  comparison: Comparison | null;
  gates: Gates | null;
  holdout: (Comparison & { baseline_run?: string; candidate_run?: string }) | null;
  decision_note: string | null;
  report: string | null;
};
