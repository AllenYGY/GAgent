# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the Application
To start the backend server:
```bash
./start_backend.sh
```

### Testing
To run tests:
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest path/to/test_file.py

# Run with verbose output
python -m pytest -v
```

### Development Commands
To format code using black:
```bash
black .
```

To check type hints:
```bash
mypy .
```

### Database Management
To initialize the database:
```bash
# Initialize main database
python -c "from app.database import init_db; init_db()"
```

To generate a demo plan for testing:
```bash
python example/generate_demo_plan.py
```

To list all plans:
```bash
python example/list_plans.py
```

To show a plan tree:
```bash
python example/show_plan_tree.py --plan 1
```

## Architecture

### High-Level Overview
The application is an AI agent system that implements task planning and execution using LLMs. The core functionality revolves around:

1. **Plan Decomposition**: Breaking down high-level goals into smaller tasks
2. **Task Execution**: Executing atomic tasks using LLMs and tools
3. **Context Management**: Maintaining context across tasks and sessions
4. **Tool Integration**: Providing external capabilities through a tool box system

### Key Components

#### Plan System

- `app/services/plans/`: Core plan functionality including decomposition and execution
- `app/repository/plan_repository.py`: Data access layer for plans
- `app/repository/plan_storage.py`: Manages SQLite storage for plans
- `app/services/plans/plan_models.py`: Data models for plans and tasks
- `app/services/plans/plan_decomposer.py`: Decomposes plans into subtasks
- `app/services/plans/plan_executor.py`: Executes plan tasks

Plans are stored in individual SQLite files in the `data/databases/plans/` directory, with metadata in the main database.

#### LLM Integration

- `app/services/llm/`: Unified LLM service with retry logic
- `app/services/foundation/settings.py`: Centralized configuration for LLM providers
- `tool_box/integration.py`: Integrates tools with LLM workflows

The system supports multiple LLM providers (Qwen, GLM, Perplexity) configured through environment variables.

#### Tool System

- `tool_box/`: MCP-compatible tool server
- `tool_box/tools_impl/`: Implementation of various tools
  - `web_search/`: Web search capabilities
  - `database_query/`: Database query tool
  - `file_operations/`: File operations
  - `graph_rag/`: Graph-based RAG
  - `internal_api/`: Internal API calls

Tools are registered and managed through the ToolBoxIntegration class.

#### Web Interface

- `app/routers/`: FastAPI routes
- `app/main.py`: FastAPI application entry point
- Frontend served from a separate repository

The backend exposes REST APIs for chat, planning, and tool operations.

### Data Flow

1. User request received via API
2. Request routed to appropriate handler
3. Plan created or retrieved from database
4. Tasks decomposed using LLM
5. Tasks executed sequentially with context propagation
6. Results aggregated and returned to user

### Configuration
Configuration is managed through environment variables in `.env`. Key settings include:

- `LLM_PROVIDER`: Main LLM provider (qwen, glm, perplexity)
- `QWEN_API_KEY`, `GLM_API_KEY`, `PERPLEXITY_API_KEY`: API keys for respective providers
- `DB_ROOT`: Database root directory
- Various timeout and retry settings for LLM calls
