import logging
import threading
from typing import Any, Dict, Optional

from ...llm import get_default_client
from ...repository.tasks import default_repo
from ...services.context.context_budget import apply_budget
from ...services.embeddings import get_embeddings_service

logger = logging.getLogger(__name__)


def _get_task_id_and_name(task) -> tuple[int, str]:
    """Support both sqlite3.Row (mapping) and tuple-style rows."""
    try:
        task_id = task["id"]  # sqlite3.Row mapping
        name = task["name"]
    except Exception:
        task_id = task[0]
        name = task[1]
    if task_id is None:
        raise ValueError("Task id is missing")
    return int(task_id), str(name)


def _fetch_prompt(task_id: int, default_prompt: str, repo: Any) -> str:
    prompt = repo.get_task_input_prompt(task_id)
    return prompt if (isinstance(prompt, str) and prompt.strip()) else default_prompt


def _glm_chat(prompt: str) -> str:
    # Delegate to default LLM client (Phase 1 abstraction)
    client = get_default_client()
    # Force real call to avoid mock responses
    return client.chat(prompt, force_real=True)


def _generate_task_embedding_async(task_id: int, content: str, repo: Any) -> None:
    """Asynchronously generate and store task embedding"""

    def _background_embedding():
        try:
            if not content or not content.strip():
                logger.debug(f"Task {task_id} content is empty, skipping embedding generation")
                return

            # Check if embedding already exists
            get_embedding = getattr(repo, "get_task_embedding", None)
            if callable(get_embedding):
                existing_embedding = get_embedding(task_id)
                if existing_embedding:
                    logger.debug(f"Task {task_id} already has embedding, skipping generation")
                    return

            embeddings_service = get_embeddings_service()

            # Generate embedding
            logger.debug(f"Generating embedding for task {task_id}")
            embedding = embeddings_service.get_single_embedding(content)

            if embedding:
                # Store embedding
                embedding_json = embeddings_service.embedding_to_json(embedding)
                store_embedding = getattr(repo, "store_task_embedding", None)
                if callable(store_embedding):
                    store_embedding(task_id, embedding_json)
                    logger.debug(f"Successfully stored embedding for task {task_id}")
            else:
                logger.warning(f"Failed to generate embedding for task {task_id}")

        except Exception as e:
            logger.error(f"Error generating embedding for task {task_id}: {e}")

    # Execute in background thread to avoid blocking main process
    thread = threading.Thread(target=_background_embedding, daemon=True)
    thread.start()


def execute_task(
    task,
    repo: Optional[Any] = None,
    use_context: bool = False,
    context_options: Optional[Dict[str, Any]] = None,
):
    repo = repo or default_repo
    task_id, name = _get_task_id_and_name(task)

    default_prompt = (
        f"Write a concise, clear section that fulfills the following task.\n"
        f"Task: {name}.\n"
        f"Length: ~200 words. Use a neutral, professional tone. Avoid domain-specific assumptions unless explicitly provided."
    )
    prompt = _fetch_prompt(task_id, default_prompt, repo)

    # Optionally include provided context bundle (legacy gather_context removed).
    bundle = None
    ctx = None
    include_deps = True
    include_plan = True
    k = 5
    manual = None
    semantic_k = None
    min_similarity = None
    max_chars_i = None
    per_section_max_i = None
    strategy = None

    if use_context:
        opts: Dict[str, Any] = context_options or {}
        try:
            include_deps = bool(opts.get("include_deps", True))
            include_plan = bool(opts.get("include_plan", True))
            try:
                k = int(opts.get("k", 5))
            except Exception:
                k = 5
            manual = opts.get("manual") if isinstance(opts.get("manual"), list) else None
            semantic_k = opts.get("semantic_k")
            min_similarity = opts.get("min_similarity")
            strategy = opts.get("strategy") if isinstance(opts.get("strategy"), str) else None

            combined = opts.get("combined")
            sections = opts.get("sections", [])
            if isinstance(combined, str) or isinstance(sections, list):
                bundle = {
                    "combined": combined or "",
                    "sections": sections if isinstance(sections, list) else [],
                }

            if bundle is not None:
                max_chars = opts.get("max_chars")
                per_section_max = opts.get("per_section_max")
                try:
                    max_chars_i = int(max_chars) if max_chars is not None else None
                except Exception:
                    max_chars_i = None
                try:
                    per_section_max_i = int(per_section_max) if per_section_max is not None else None
                except Exception:
                    per_section_max_i = None

                if max_chars_i is not None or per_section_max_i is not None:
                    bundle = apply_budget(
                        bundle,
                        max_chars=max_chars_i,
                        per_section_max=per_section_max_i,
                        strategy=strategy or "truncate",
                    )

            ctx = bundle.get("combined") if isinstance(bundle, dict) else None
        except Exception:
            ctx = None

        if ctx:
            prompt = f"[Context]\n\n{ctx}\n\n[Task Instruction]\n\n{prompt}"

        # Optional: persist context snapshot if requested
        try:
            if isinstance(bundle, dict) and bool(opts.get("save_snapshot", False)):
                label = opts.get("label") or "latest"
                meta = {
                    "source": "executor",
                    "options": {
                        "include_deps": include_deps,
                        "include_plan": include_plan,
                        "k": k,
                        "manual": manual,
                        "semantic_k": semantic_k,
                        "min_similarity": min_similarity,
                        "max_chars": max_chars_i,
                        "per_section_max": per_section_max_i,
                        "strategy": strategy or "truncate",
                    },
                }
                if "budget_info" in bundle:
                    meta["budget_info"] = bundle["budget_info"]
                upsert_context = getattr(repo, "upsert_task_context", None)
                if callable(upsert_context):
                    upsert_context(
                        task_id,
                        bundle.get("combined", ""),
                        bundle.get("sections", []),
                        meta,
                        label=label,
                    )
        except Exception:
            pass

    try:
        content = _glm_chat(prompt)
        upsert_output = getattr(repo, "upsert_task_output", None)
        if callable(upsert_output):
            upsert_output(task_id, content)
        logger.info(f"Task {task_id} ({name}) done.")

        # Asynchronously generate embedding (optional)
        try:
            generate_embeddings = True  # Default enabled

            # Check if there's embedding configuration in context_options
            if context_options and isinstance(context_options, dict):
                generate_embeddings = context_options.get("generate_embeddings", True)

            if generate_embeddings:
                _generate_task_embedding_async(task_id, content, repo)
        except Exception as embed_error:
            logger.warning(f"Failed to trigger embedding generation (task {task_id}): {embed_error}")

        return "done"
    except Exception as e:
        logger.error(f"Task {task_id} ({name}) failed: {e}")
        return "failed"
