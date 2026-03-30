# Web Search Execution Plan

## Executive Summary

Add a backend-managed web search capability to the existing agent without rewriting the architecture. The current project already has the right integration seams:

- Flask API routes live in `backend/assistant_backend/api/app.py`
- agent orchestration lives in `backend/assistant_backend/core/orchestrator.py`
- tool modules live in `backend/assistant_backend/tools/`
- runtime settings live in `backend/assistant_backend/config.py`
- SQLite state already exists in `backend/assistant_backend/storage/database.py`

The cleanest implementation is a provider-agnostic `web_search` tool wired into the current planner -> generator -> validator loop. The agent should be able to:

1. ask for `web_search` in strict JSON
2. run the tool in the backend
3. append sanitized search results back into the model prompt
4. continue generation for up to 3 tool iterations
5. still enforce the existing `FILE:` output format and retry rules

## Important Repo-Specific Decisions

### 1. Keep Flask, do not replatform to FastAPI

Your research mentions FastAPI for the sample endpoint, but this repository is already built around Flask routes in `backend/assistant_backend/api/app.py`. The search-test endpoint should be added there, not by introducing a second web framework.

### 2. Use a provider-agnostic search adapter layer

The tool should expose one stable interface:

`web_search(query, num_results=5, provider=None) -> list[SearchResult]`

Internally, it can support:

- `brave`
- `serpapi`
- `bing`

This keeps the orchestrator simple and avoids coupling agent logic to one vendor.

### 3. Prefer requests-based adapters over SDK lock-in

This repo already depends on `requests`, so the first implementation should use direct HTTP calls instead of adding multiple provider SDKs. This keeps installation lighter and matches the current backend style.

Practical recommendation for this repo:

- implement `brave` first as the default requests-based engine
- implement `serpapi` second behind the same adapter interface
- leave `bing` as a stub or low-priority adapter unless Azure is already required

Reasoning:

- Brave’s official API is simple REST with `X-Subscription-Token` and a stable JSON response format.
- SerpApi is viable, but its Python integration page currently warns that the older package is being deprecated in favor of a newer implementation, so we should avoid hard-wiring the legacy client as a core dependency.
- Bing is workable, but it adds Azure-specific setup and is usually the least cost-effective option for this project.

### 4. Reuse the existing SQLite state DB for cache + tool logs

Do not introduce a separate cache dependency in phase 1. Extend `.assistant/state.db` with:

- `web_search_cache`
- `tool_invocations`

This matches the current runtime model and avoids additional operational complexity.

### 5. Keep web search backend-only

The renderer should never call web providers directly. The frontend continues talking only to the backend, and all API keys remain server-side.

## Implementation Scope

### In scope

- backend web search tool
- provider adapters for Brave and SerpApi
- optional Bing adapter stub
- tool registry
- JSON tool-call parsing in the main agent loop
- search result injection back into generation
- cache + tool logging
- search test API endpoint
- unit and integration tests

### Out of scope for phase 1

- frontend search UI
- streaming partial tool events to the UI
- browser automation / scraping
- image/video/news-specific search flows
- ranking fusion across multiple search providers
- citation-aware answer rendering in the frontend

## Proposed Files To Add Or Modify

### New files

- `backend/assistant_backend/tools/web_search.py`
- `backend/assistant_backend/tools/tool_registry.py`
- `tests/test_web_search.py`
- `tests/test_orchestrator_web_search.py`

### Modified files

- `backend/assistant_backend/tools/__init__.py`
- `backend/assistant_backend/core/orchestrator.py`
- `backend/assistant_backend/core/models.py`
- `backend/assistant_backend/core/executor.py`
- `backend/assistant_backend/api/app.py`
- `backend/assistant_backend/config.py`
- `backend/assistant_backend/storage/database.py`
- `pyproject.toml`
- `requirements.txt`
- `README.md`

## Target Design

### Search result schema

Every adapter must normalize results into this shape:

```json
{
  "title": "string",
  "link": "https://example.com/page",
  "snippet": "short sanitized text",
  "source": "example.com",
  "published_at": "2026-03-28T00:00:00Z or empty string"
}
```

### Tool-call contract from the model

The orchestrator should recognize a strict JSON object like:

```json
{
  "tool": "web_search",
  "query": "latest FastAPI best practices 2026",
  "num_results": 5
}
```

Rules:

- only accept this format when the whole model response parses as JSON
- ignore tool calls in Ask mode for phase 1
- allow tool calls in Agent mode and optionally Plan mode later
- max 3 tool iterations per user request

### Result injection format

After search completes, append a compact structured block back into the prompt:

```text
Web search results:
1. Title (source) - snippet
   Link: https://...
2. ...

Use these results when generating the remaining files.
Keep the output in strict FILE format.
```

Keep this compact to reduce Groq TPM pressure.

## Detailed Execution Steps

### Phase 1. Add configuration and provider selection

Modify `backend/assistant_backend/config.py` to support:

- `WEB_SEARCH_ENABLED`
- `WEB_SEARCH_PROVIDER`
- `WEB_SEARCH_TIMEOUT_SECONDS`
- `WEB_SEARCH_MAX_RESULTS`
- `WEB_SEARCH_CACHE_TTL_SECONDS`
- `BRAVE_SEARCH_API_KEY`
- `SERPAPI_API_KEY`
- `BING_SEARCH_API_KEY`

Implementation notes:

- default `WEB_SEARCH_PROVIDER` to `brave`
- keep provider choice runtime-configurable
- expose web search config in `to_public_dict()` without exposing secrets

### Phase 2. Extend SQLite state for cache and logs

Modify `backend/assistant_backend/storage/database.py`:

- add `web_search_cache` table
- add `tool_invocations` table
- add helpers like:
  - `get_cached_search(provider, query_hash)`
  - `store_cached_search(provider, query_hash, response_json, expires_at)`
  - `log_tool_invocation(session_id, tool_name, request_json, response_json, success, error)`

Recommended schema:

- `web_search_cache(provider TEXT, query_hash TEXT, response_json TEXT, created_at TEXT, expires_at TEXT, PRIMARY KEY(provider, query_hash))`
- `tool_invocations(id TEXT PRIMARY KEY, session_id TEXT, tool_name TEXT, request_json TEXT, response_json TEXT, success INTEGER, error_text TEXT, created_at TEXT)`

### Phase 3. Add the web search tool module

Create `backend/assistant_backend/tools/web_search.py`.

Responsibilities:

- provider adapter selection
- query normalization
- cache lookup/write
- rate-limit handling with short retry/backoff
- HTTP requests via `requests`
- URL sanitization
- snippet truncation
- shape normalization to `SearchResult`

Recommended internal functions:

- `_normalize_query(query: str) -> str`
- `_hash_query(query: str) -> str`
- `_sanitize_link(url: str) -> str`
- `_truncate_snippet(text: str, max_chars: int = 200) -> str`
- `_search_brave(query: str, num_results: int) -> list[dict[str, str]]`
- `_search_serpapi(query: str, num_results: int) -> list[dict[str, str]]`
- `_search_bing(query: str, num_results: int) -> list[dict[str, str]]`
- `web_search(query: str, num_results: int = 5, provider: str | None = None, session_id: str | None = None) -> list[dict[str, str]]`

Adapter notes:

#### Brave

- endpoint: `https://api.search.brave.com/res/v1/web/search`
- auth header: `X-Subscription-Token`
- params: `q`, `count`, optionally `country`, `search_lang`
- parse the web results array and map to normalized output

#### SerpApi

- use direct HTTP requests instead of locking to the deprecated legacy Python package
- support Google web results first
- parse `organic_results`

#### Bing

- add interface-compatible stub or optional implementation
- do not block phase 1 on Bing unless already needed

### Phase 4. Add a tool registry

Create `backend/assistant_backend/tools/tool_registry.py` and update `backend/assistant_backend/tools/__init__.py`.

Goal:

- central place to register callable backend tools
- avoid scattering tool dispatch logic in the orchestrator

Suggested interface:

- `TOOLS = {"web_search": web_search}`
- `run_tool(name: str, **kwargs) -> Any`

### Phase 5. Add tool-call detection to the agent loop

Modify `backend/assistant_backend/core/orchestrator.py`.

Add a structured tool loop inside `run_agent_mode`:

1. call model
2. inspect response
3. if response is a valid `web_search` tool request:
   - run tool
   - store tool log
   - append results to prompt context
   - re-call model
4. repeat until:
   - non-tool content is returned, or
   - tool loop reaches max iterations

Important constraints:

- do not break the existing `FILE:` generation + validation flow
- do not remove current retry logic
- separate tool-iteration count from output-validation retry count

Recommended structure:

- keep `build_agent_prompt()` for generation rules
- add helpers:
  - `_parse_tool_call(response_text)`
  - `_format_search_results_for_prompt(results)`
  - `_run_tool_iteration(...)`

### Phase 6. Tighten prompt rules for tool usage

Update the agent prompt contract in `backend/assistant_backend/core/orchestrator.py`.

Add rules like:

- If external or recent information is required, reply with JSON only using the `web_search` tool contract.
- Do not mix tool JSON and `FILE:` blocks in the same response.
- After tool results are provided, continue with strict `FILE:` output.

Also keep current rules:

- no markdown fences
- no explanations outside structure + `FILE:` blocks
- no early stopping

### Phase 7. Keep and extend current validation

Modify `backend/assistant_backend/core/executor.py` only where necessary.

Validation changes:

- keep existing `FILE:` block validation
- if a tool-call response was expected but the response is malformed JSON, retry
- if the tool loop returns no usable search results, inject a corrective retry instruction
- keep duplicate `FILE:` recovery behavior

### Phase 8. Add a backend search-test endpoint

Modify `backend/assistant_backend/api/app.py`.

Add:

- `POST /api/agent/search-test`

Payload:

```json
{
  "query": "latest FastAPI best practices 2026",
  "numResults": 5,
  "provider": "brave"
}
```

Response:

- normalized results
- cache hit/miss metadata if available

This endpoint is for backend verification only, not a user-facing browsing UI.

### Phase 9. Add tests

Add `tests/test_web_search.py`:

- mock Brave response
- mock SerpApi response
- verify normalization shape
- verify snippet truncation
- verify URL sanitization
- verify cache hit path
- verify graceful failure on HTTP 429 / 5xx

Add `tests/test_orchestrator_web_search.py`:

- simulate model returning `{"tool":"web_search", ...}`
- confirm tool is invoked
- confirm results are appended back into prompt
- confirm final model output still passes `FILE:` validation
- confirm max tool iterations are enforced

Use Flask’s test client and monkeypatch `requests.get` / `requests.post` rather than real network calls.

## Output Parsing Strategy

### Tool call parser

Accept tool JSON only when:

- the full response parses as JSON
- `tool == "web_search"`
- `query` is a non-empty string
- `num_results` or `num` is an integer within bounds

Reject and retry when:

- JSON is malformed
- tool name is unknown
- result schema is incomplete

### Final generation parser

Keep the current `FILE:` parsing rules, plus:

- if search happened, ensure the final response is no longer a tool JSON block
- if output is still tool JSON after max tool iterations, fail with a clear error

## Rate Limiting, Caching, and Safety

### Caching

Recommended defaults:

- cache TTL: 15 minutes for general web search
- hash query + provider + num_results into cache key
- do not cache provider failures

### Rate limiting

Recommended safeguards:

- max `num_results` = 8
- max tool calls per request = 3
- short per-request timeout
- bounded retry/backoff for 429 and transient 5xx

### Safety

- strip tracking query params from returned URLs when possible
- truncate snippets before reinserting into prompts
- never pass raw HTML into model context
- log tool usage but avoid storing secrets

## Acceptance Criteria

The work is complete when all of the following are true:

1. Agent mode can issue a `web_search` tool call and continue generation afterward.
2. Search results are normalized into one consistent schema regardless of provider.
3. Search cache is persisted in `.assistant/state.db`.
4. Tool invocations are logged for debugging.
5. `POST /api/agent/search-test` returns normalized results.
6. Existing `FILE:` validation and retry flow still works.
7. Tests cover both the tool and orchestrator integration.
8. No API keys are exposed to the frontend.

## Recommended Rollout Order

1. Config + storage schema
2. `web_search.py` with Brave adapter
3. tool registry
4. orchestrator tool-call loop
5. search-test endpoint
6. tests
7. SerpApi adapter
8. Bing stub / optional adapter

## Known Risks

- Tool-calling can increase Groq token pressure if result injection is too verbose.
- Search providers can rate-limit independently from the LLM provider.
- Prompt quality may degrade if snippets are too long or noisy.
- Search results can be stale or low-quality without result ranking heuristics.

Mitigations:

- compact result formatting
- cache + short retries
- strict prompt budget on injected results
- keep source links in normalized output

## References

- Brave Search API: [https://brave.com/search/api/](https://brave.com/search/api/)
- SerpApi Python integration note: [https://serpapi.com/integrations/python](https://serpapi.com/integrations/python)
- Flask testing docs: [https://flask.palletsprojects.com/testing/](https://flask.palletsprojects.com/testing/)

## Final Recommendation

Implement this in two layers:

- phase 1: Brave-backed `web_search` + tool loop + tests
- phase 2: SerpApi adapter + optional Bing support

That path fits the current repository best because it reuses:

- the existing Flask API surface
- the current SQLite runtime state
- the current `requests` dependency
- the current orchestrator-centered agent flow

It also avoids a risky rewrite while still giving the agent a real web-search capability that can improve version accuracy, framework API correctness, and up-to-date code generation.
