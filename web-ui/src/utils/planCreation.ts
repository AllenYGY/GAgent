import { ChatActionSummary } from '@/types';
import { extractPlanTitleFromActions } from '@utils/planSyncEvents';

const PLAN_CREATION_ACTIONS = new Set(['create_plan', 'clone_plan', 'import_plan']);

export interface DecompositionJobInfo {
  jobId: string;
  jobType?: string | null;
  status?: string | null;
  planId?: number | null;
}

export const hasPlanCreationAction = (actions: ChatActionSummary[]): boolean => {
  return actions.some((action) => {
    const kind = (action.kind ?? '').toString().toLowerCase();
    const name = (action.name ?? '').toString().toLowerCase();
    return kind === 'plan_operation' && PLAN_CREATION_ACTIONS.has(name);
  });
};

export const getPlanCreationTitle = (
  actions: ChatActionSummary[],
  fallback?: string | null
): string | null => {
  const inferredTitle = extractPlanTitleFromActions(actions);
  if (typeof inferredTitle === 'string' && inferredTitle.trim().length > 0) {
    return inferredTitle.trim();
  }
  if (typeof fallback === 'string' && fallback.trim().length > 0) {
    return fallback.trim();
  }
  return null;
};

const coerceJobInfo = (value: any): DecompositionJobInfo | null => {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const rawId = (value as any).job_id ?? (value as any).jobId;
  if (!rawId) {
    return null;
  }
  return {
    jobId: String(rawId),
    jobType: typeof (value as any).job_type === 'string' ? (value as any).job_type : null,
    status: typeof (value as any).status === 'string' ? (value as any).status : null,
    planId: typeof (value as any).plan_id === 'number' ? (value as any).plan_id : null,
  };
};

export const extractDecompositionJob = (
  items: Array<Record<string, any>>
): DecompositionJobInfo | null => {
  for (const item of items) {
    const details =
      item?.details && typeof item.details === 'object' ? item.details : item;
    const jobCandidate =
      details?.decomposition_job ??
      details?.decompositionJob ??
      details?.job ??
      null;
    const jobInfo = coerceJobInfo(jobCandidate);
    if (jobInfo) {
      return jobInfo;
    }
  }
  return null;
};
