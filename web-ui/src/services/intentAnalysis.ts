import { chatApi } from '@api/chat';
import { planTreeApi } from '@api/planTree';
import type { DecomposeTaskPayload } from '@api/planTree';
import type { DecompositionJobStatus } from '@/types';
import { SessionTaskSearch } from '@utils/taskSearch';
import { planTreeToTasks } from '@utils/planTree';
import { ENV } from '@/config/env';
import type { ChatSession, Task } from '@/types';

// Intent analysis result interface
export interface IntentAnalysisResult {
  needsToolCall: boolean;
  toolType?: string;
  confidence: number;
  reasoning: string;
  extractedParams?: Record<string, any>;
}

// Tool execution result interface
export interface ToolExecutionResult {
  handled: boolean;
  response: string;
  metadata?: Record<string, any>;
}

/**
 * Intelligent intent analysis – ask the LLM whether a tool invocation is required.
 */
export async function analyzeUserIntent(
  userInput: string, 
  context: {
    currentSession?: ChatSession | null;
    currentWorkflowId?: string | null;
    recentMessages?: Array<{role: string; content: string; timestamp: string}>;
  }
): Promise<IntentAnalysisResult> {
  
  const analysisPrompt = `You are an intelligent assistant. Analyse the user's input and decide whether a tool needs to be invoked.

User input: """${userInput}"""

Context:
- Current session ID: ${context.currentSession?.session_id || 'none'}
- Current workflow ID: ${context.currentWorkflowId || 'none'}
- Recent dialogue: ${
    context.recentMessages?.map((m) => `${m.role}: ${m.content}`).join('\n') || 'none'
  }

Available tool types:
1. task_search - search for tasks in the current workspace
2. task_create - create a brand-new ROOT task
3. task_decompose - break down an existing task (ROOT → COMPOSITE → ATOMIC)
4. system_status - inspect the current system status
5. general_chat - plain conversation without tool usage

Analyse the intent and return JSON with the following structure:
{
  "needsToolCall": boolean, // whether a tool call is required
  "toolType": string, // tool type when needsToolCall is true
  "confidence": number, // confidence score between 0 and 1
  "reasoning": string, // explanation for the decision
  "extractedParams": {} // parameters extracted from the request
}

Guidelines:
- If the user wants to view, search, or list existing tasks -> task_search
- If the user wants to create an entirely new task with no prior context -> task_create
- If the user wants to split, refine, or break down an existing task -> task_decompose
  * Keywords: split, decompose, refine, expand, detailed plan, subtasks
  * Context: if a task was just created and the user now asks to split it, choose task_decompose
- If the user asks about system status or health -> system_status
- Otherwise -> general_chat

Pay special attention to context:
- If a task was just created and the user now says "split", "decompose", etc., choose task_decompose (not task_create).

Return JSON only. Do not include any additional text.`;

  try {
    console.log('🧠 Sending intent analysis request...');
    
    const response = await chatApi.sendMessage(analysisPrompt, {
      mode: 'analyzer',
      workflow_id: context.currentWorkflowId,
      session_id: context.currentSession?.session_id,
      // 🔒 Mark as an internal analysis request to avoid creating workflows
      metadata: {
        internal_analysis: true,
        original_user_input: userInput
      }
    });
    
    console.log('🧠 Raw LLM intent analysis response:', response.response);
    
    // Parse the JSON returned by the LLM
    const jsonMatch = response.response.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.warn('🧠 Unable to parse LLM response as JSON; using default values.');
      return {
        needsToolCall: false,
        confidence: 0.1,
        reasoning: 'Unable to parse LLM response',
        toolType: 'general_chat'
      };
    }
    
    const result = JSON.parse(jsonMatch[0]);
    console.log('🧠 Parsed intent analysis result:', result);
    
    return {
      needsToolCall: result.needsToolCall || false,
      toolType: result.toolType || 'general_chat',
      confidence: result.confidence || 0.5,
      reasoning: result.reasoning || 'Automatic analysis',
      extractedParams: result.extractedParams || {}
    };
    
  } catch (error) {
    console.error('🧠 Intent analysis failed:', error);
    // Fall back to a simple chat response
    return {
      needsToolCall: false,
      confidence: 0.1,
      reasoning: `Analysis failed: ${error}`,
      toolType: 'general_chat'
    };
  }
}

/**
 * Execute the corresponding tool based on the analysed intent.
 */
export async function executeToolBasedOnIntent(
  intent: IntentAnalysisResult,
  context: {
    currentSession?: ChatSession | null;
    currentWorkflowId?: string | null;
    currentPlanId?: number | null;
    userInput: string;
  }
): Promise<ToolExecutionResult> {
  
  console.log(`🔧 Executing tool: ${intent.toolType}`, intent);
  
  try {
    switch (intent.toolType) {
      case 'task_create':
        return await executeTaskCreate(context.userInput, context);
      case 'task_search':
        return await executeTaskSearch(context.userInput, context);
      case 'task_decompose':
        return await executeTaskDecompose(context.userInput, context, intent);
      case 'system_status':
        return await executeSystemStatus();
      default:
        return {
          handled: false,
          response: '',
          metadata: { needsToolCall: false }
        };
    }
  } catch (error) {
    console.error(`🔧 Tool execution failed (${intent.toolType}):`, error);
    return {
      handled: false,
      response: `Tool execution error: ${error}`
    };
  }
}

/**
 * Execute the task search helper.
 */
async function executeTaskSearch(
  userInput: string,
  context: {
    currentSession?: ChatSession | null;
    currentWorkflowId?: string | null;
    currentPlanId?: number | null;
  }
): Promise<ToolExecutionResult> {

  const searchResult = await SessionTaskSearch.searchCurrentSessionTasks(
    userInput,
    context.currentSession,
    context.currentWorkflowId,
    context.currentPlanId
  );
  
  const response = SessionTaskSearch.formatSearchResults(
    searchResult.tasks,
    searchResult.summary
  );
  
  return {
    handled: true,
    response,
    metadata: {
      tasks_found: searchResult.total,
      search_query: userInput
    }
  };
}

/**
 * Execute the task creation helper.
 */
async function executeTaskCreate(
  userInput: string,
  context: {
    currentSession?: ChatSession | null;
    currentWorkflowId?: string | null;
    currentPlanId?: number | null;
  }
): Promise<ToolExecutionResult> {
  return {
    handled: true,
    response:
      'ℹ️ Please describe the task or plan you want to create and I will handle it in the conversation flow.',
    metadata: {
      action: 'create_task',
      success: false,
    },
  };
}

/**
 * Execute the system status helper.
 */
async function executeSystemStatus(): Promise<ToolExecutionResult> {
  
  try {
    const response = await fetch(`${ENV.API_BASE_URL}/system/health`);
    if (!response.ok) {
      throw new Error(`system/health ${response.status}`);
    }
    const status = await response.json();

    const summary = `📊 **System Status Report**\n\n🏥 **Overall health**: ${
      status.overall_status === 'healthy' ? '✅ Healthy' :
      status.overall_status === 'degraded' ? '⚠️ Degraded' : '❌ Critical'
    }\n\n` +
      `📦 Components: ${(status.components && Object.keys(status.components).length) || 0}\n` +
      `💡 Recommendations: ${(status.recommendations || []).join('; ') || 'None'}`;

    return {
      handled: true,
      response: summary,
      metadata: {
        system_health: status.overall_status,
        components: status.components,
      }
    };
  } catch (error) {
    return {
      handled: true,
      response: `❌ Failed to fetch system status: ${error}`,
      metadata: {
        error: String(error)
      }
    };
  }
}

/**
 * 🧠 Use the LLM to select the target task – relies purely on semantic understanding.
 */
async function selectTargetTaskWithLLM(userInput: string, tasks: Task[]): Promise<Task | null> {
  try {
    if (!tasks || tasks.length === 0) {
      return null;
    }
    
    // Build a textual description of available tasks
    const taskDescriptions = tasks.map((task, index) => {
      const typeLabel =
        task.task_type === 'root'
          ? 'ROOT'
          : task.task_type === 'composite'
          ? 'COMPOSITE'
          : 'ATOMIC';
      return `[${index + 1}] ID: ${task.id}, Name: "${task.name}", Type: ${typeLabel}, Depth: ${task.depth}`;
    }).join('\n');
    
    // 🧠 Ask the LLM to determine which task should be decomposed
    const prompt = `Determine which task the user wants to decompose.

User input: "${userInput}"

Current task list:
${taskDescriptions}

Decomposition rules:
- ROOT tasks (depth 0) can be decomposed into COMPOSITE tasks (depth 1)
- COMPOSITE tasks (depth 1) can be decomposed into ATOMIC tasks (depth 2)
- ATOMIC tasks (depth 2) are leaf nodes and cannot be decomposed further

Analyse the user intent and return JSON only (no explanations):
{
  "target_task_id": <task ID>,
  "reasoning": "<why this task was selected>"
}

If the user is not explicit, apply these defaults:
1. If a ROOT task exists without children → select the ROOT task
2. If the ROOT already has children but a COMPOSITE task is not decomposed → select the first COMPOSITE task
3. If the user references "the Nth task", choose that index.`;

    const response = await chatApi.sendMessage(prompt, { mode: 'assistant' });
    console.log('🧠 LLM task selection response:', response);
    
    // Parse the LLM response
    try {
      const match = response.response.match(/\{[\s\S]*\}/);
      if (!match) {
        console.warn('⚠️ LLM did not return valid JSON; falling back to default strategy.');
        return selectDefaultTask(tasks);
      }
      
      const result = JSON.parse(match[0]);
      const targetTaskId = result.target_task_id;
      
      // Locate the corresponding task
      const targetTask = tasks.find(t => t.id === targetTaskId);
      if (targetTask) {
        console.log(`✅ LLM chose task: ${targetTask.name} (ID: ${targetTask.id})`);
        return targetTask;
      }
    } catch (parseError) {
      console.warn('⚠️ Failed to parse LLM response; using default strategy:', parseError);
    }
    
    // Fall back to default selection when the LLM fails
    return selectDefaultTask(tasks);
    
  } catch (error) {
    console.error('❌ LLM task selection failed:', error);
    return selectDefaultTask(tasks);
  }
}

/**
 * Default task selection strategy (fallback when the LLM cannot decide).
 */
function selectDefaultTask(tasks: Task[]): Task | null {
  // Prefer a ROOT task without children
  const rootTasks = tasks.filter(t => t.task_type === 'root' && !t.parent_id);
  if (rootTasks.length > 0) {
    const rootTask = rootTasks[rootTasks.length - 1];
    // Ensure it has no children
    const hasChildren = tasks.some(t => t.parent_id === rootTask.id);
    if (!hasChildren) {
      return rootTask;
    }
  }
  
  // Otherwise pick the first COMPOSITE task without children
  const compositeTasks = tasks.filter(t => t.task_type === 'composite');
  for (const composite of compositeTasks) {
    const hasChildren = tasks.some(t => t.parent_id === composite.id);
    if (!hasChildren) {
      return composite;
    }
  }
  
  // Fallback: return the most recent ROOT task
  return rootTasks.length > 0 ? rootTasks[rootTasks.length - 1] : null;
}

/**
 * Execute the task decomposition helper for an existing task.
 */
async function executeTaskDecompose(
  userInput: string,
  context: {
    currentSession?: ChatSession | null;
    currentWorkflowId?: string | null;
    currentPlanId?: number | null;
  },
  analysis: any
): Promise<ToolExecutionResult> {
  const planId = context.currentPlanId;
  if (!planId) {
    return {
      handled: true,
      response:
        '❌ **Task decomposition failed**\n\n🚫 The current session is not bound to a plan, so no node can be decomposed.',
      metadata: {
        action: 'task_decompose',
        success: false,
        error: 'missing_plan_id',
      },
    };
  }

  try {
    const tree = await planTreeApi.getPlanTree(planId);
    const tasks = planTreeToTasks(tree);
    const targetTask = await selectTargetTaskWithLLM(userInput, tasks);

    if (!targetTask) {
      return {
        handled: true,
        response:
          '❌ **Task decomposition failed**\n\n🚫 No eligible target task was found. Please verify that a ROOT or COMPOSITE task is available.',
        metadata: {
          action: 'task_decompose',
          success: false,
          error: 'no_target_task',
        },
      };
    }

    const payload: DecomposeTaskPayload = {
      plan_id: planId,
      async_mode: true,
    };

    if (typeof analysis?.extractedParams?.expand_depth === 'number') {
      payload.expand_depth = analysis.extractedParams.expand_depth;
    }
    if (typeof analysis?.extractedParams?.node_budget === 'number') {
      payload.node_budget = analysis.extractedParams.node_budget;
    }
    if (typeof analysis?.extractedParams?.allow_existing_children === 'boolean') {
      payload.allow_existing_children = analysis.extractedParams.allow_existing_children;
    }

    const decomposition = await planTreeApi.decomposeTask(targetTask.id, payload);

    const jobInfo: DecompositionJobStatus | null = decomposition.job || null;
    const jobId = jobInfo?.job_id ?? decomposition.result?.job_id ?? null;
    const responseText = `🧠 **Task decomposition started**\n\n📋 Target task: ${targetTask.name} (ID: ${targetTask.id})\n⏱️ The job is running in the background and generating child tasks.\nCheck the job log panel for live updates.`;

    return {
      handled: true,
      response: responseText,
      metadata: {
        action: 'task_decompose',
        success: true,
        target_task_id: targetTask.id,
        target_task_name: targetTask.name,
        plan_id: planId,
        type: 'job_log',
        job_id: jobId,
        job_status: jobInfo?.status ?? 'queued',
        job: jobInfo,
        job_logs: jobInfo?.logs ?? [],
      },
    };
  } catch (error) {
    console.error('Task decomposition failed:', error);
    return {
      handled: true,
      response: `❌ **Task decomposition failed**\n\n🚫 System error: ${error}`,
      metadata: {
        action: 'task_decompose',
        success: false,
        error: String(error),
      },
    };
  }
}
