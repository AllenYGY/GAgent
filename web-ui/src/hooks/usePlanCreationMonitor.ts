import { useEffect } from 'react';
import { planTreeApi } from '@api/planTree';
import { queryClient } from '@/queryClient';
import { useChatStore } from '@store/chat';
import { dispatchPlanSyncEvent } from '@utils/planSyncEvents';

const FINAL_JOB_STATUSES = new Set(['succeeded', 'failed']);
const POLL_INTERVAL_MS = 4000;

export const usePlanCreationMonitor = () => {
  const pendingPlanCreation = useChatStore((state) => state.pendingPlanCreation);
  const setPendingPlanCreation = useChatStore((state) => state.setPendingPlanCreation);
  const updatePendingPlanCreation = useChatStore((state) => state.updatePendingPlanCreation);

  useEffect(() => {
    if (!pendingPlanCreation) {
      return undefined;
    }

    let cancelled = false;
    let timerId: number | null = null;

    const poll = async () => {
      if (cancelled) {
        return;
      }

      const { planId, jobId } = pendingPlanCreation;

      queryClient.invalidateQueries({ queryKey: ['planTree', 'summaries'], exact: false });
      if (planId != null) {
        queryClient.invalidateQueries({ queryKey: ['planTree', 'tasks', planId], exact: true });
        queryClient.invalidateQueries({ queryKey: ['planTree', 'results', planId], exact: false });
        queryClient.invalidateQueries({ queryKey: ['planTree', 'execution', planId], exact: false });
      }

      if (jobId) {
        try {
          const snapshot = await planTreeApi.getJobStatus(jobId);
          if (cancelled) {
            return;
          }

          const nextPlanId =
            typeof snapshot.plan_id === 'number' ? snapshot.plan_id : pendingPlanCreation.planId;
          const nextJobStatus =
            typeof snapshot.status === 'string' ? snapshot.status : pendingPlanCreation.jobStatus;
          const nextJobType =
            typeof snapshot.job_type === 'string' ? snapshot.job_type : pendingPlanCreation.jobType;

          if (
            nextPlanId !== pendingPlanCreation.planId ||
            nextJobStatus !== pendingPlanCreation.jobStatus ||
            nextJobType !== pendingPlanCreation.jobType
          ) {
            updatePendingPlanCreation({
              planId: nextPlanId ?? null,
              jobStatus: nextJobStatus ?? null,
              jobType: nextJobType ?? null,
            });
          }

          if (
            snapshot.status &&
            FINAL_JOB_STATUSES.has(snapshot.status) &&
            nextJobType !== 'chat_action'
          ) {
            setPendingPlanCreation(null);
            dispatchPlanSyncEvent(
              {
                type: 'plan_jobs_completed',
                plan_id: nextPlanId ?? null,
                plan_title: null,
                job_id: jobId,
                job_type: nextJobType ?? null,
                status: snapshot.status,
              },
              {
                source: 'plan.creation',
                jobId,
                jobType: nextJobType ?? null,
                status: snapshot.status,
              }
            );
            return;
          }
        } catch (error) {
          console.warn('Failed to poll plan creation job status:', error);
        }
      }

      timerId = window.setTimeout(poll, POLL_INTERVAL_MS);
    };

    timerId = window.setTimeout(poll, 1000);

    return () => {
      cancelled = true;
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
    };
  }, [pendingPlanCreation, setPendingPlanCreation, updatePendingPlanCreation]);
};
