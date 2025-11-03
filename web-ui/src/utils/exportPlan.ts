import { planTreeApi } from '@api/planTree';

const sanitizeFileName = (rawTitle: string, planId: number): string => {
  const fallback = `plan_${planId}`;
  const trimmed = (rawTitle ?? '').trim();
  const safeBase = (trimmed || fallback).replace(/[\\s/:*?"<>|]+/g, '_').slice(0, 60);
  return safeBase || fallback;
};

export const exportPlanAsJson = async (
  planId: number,
  planTitle?: string | null
): Promise<string> => {
  if (!planId || Number.isNaN(planId)) {
    throw new Error('A valid plan id is required to export.');
  }

  try {
    const tree = await planTreeApi.getPlanTree(planId);
    const titleFromTree = tree?.title ?? undefined;
    const baseName = sanitizeFileName(planTitle ?? titleFromTree ?? '', planId);
    const timestamp = new Date().toISOString().replace(/[:]/g, '-');
    const fileName = `${baseName}_${planId}_${timestamp}.json`;

    const content = JSON.stringify(tree, null, 2);
    const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    return fileName;
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to export plan: ${reason}`);
  }
};

