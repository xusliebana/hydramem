# Client LLM Bridge / Provider 🟡

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Mid-term bet — useful integration, but requires a careful trust boundary

## Why it matters

HydraMem currently treats LLM access as an internal provider choice:
Ollama, OpenAI, Anthropic, or Mistral. MCP clients such as VS Code Copilot,
Cursor, Claude Desktop, and OpenCode call HydraMem tools, but HydraMem cannot
automatically call the client's own model back.

For some users, that creates duplicated configuration:

- the client already has a high-quality authenticated model
- HydraMem still needs separate LLM credentials or a local Ollama daemon for
  VoG, conflict detection, and Night Gardener relation inference
- organisations may want all model usage to flow through the editor/client
  policy layer rather than through HydraMem directly

A **Client LLM Bridge** would add an explicit provider mode where HydraMem
delegates completion requests to a local client-side adapter. The adapter may
then call VS Code's Language Model API, a Copilot-backed extension surface, or
another client-owned LLM capability, depending on what the client exposes.

This must be opt-in. MCP by itself is client → server tool invocation; it does
not grant the server a general ability to call the client's private model.

## State of the art

- **VS Code Language Model API** — extension-facing model access, gated by
  VS Code / extension capabilities rather than exposed as a generic local HTTP
  API.
- **MCP host/tool split** — clients call servers; reverse model calls require
  an explicit sidecar or callback protocol.
- **OpenAI-compatible local gateways** — common pattern for normalising model
  providers behind a small HTTP endpoint.
- **Editor policy layers** — enterprise deployments often centralise model
  access in the IDE or agent host.

## Proposed architecture

Add a new `LLMProvider` implementation that speaks to a local adapter endpoint:

```text
HydraMem VoG / Inferrer / ConflictChecker
        │
        ▼
ClientLLMProvider.complete(prompt)
        │ HTTP localhost / stdio sidecar
        ▼
Client-side adapter
        │
        ├── VS Code extension using Language Model API
        ├── Cursor/OpenCode adapter
        └── custom OpenAI-compatible gateway
        │
        ▼
Client-owned LLM response
```

Configuration sketch:

```yaml
llm:
  provider: client
  client:
    endpoint: http://127.0.0.1:8766/v1/complete
    timeout_seconds: 60
    auth_token_env: HYDRAMEM_CLIENT_LLM_TOKEN
    fallback_provider: ollama   # ollama | openai | anthropic | mistral | none

verification:
  vog_use_local_llm: false      # allow VoG to use llm.provider=client
```

Provider contract:

```python
class ClientLLMProvider:
    name = "client"

    def complete(self, prompt: str, model: str | None = None) -> str:
        ...
```

The endpoint should accept a minimal JSON payload:

```json
{
  "prompt": "...",
  "model": null,
  "purpose": "vog"
}
```

And return:

```json
{
  "text": "GROUNDED\nCONFIDENCE: 0.91"
}
```

No chain-of-thought, hidden scratchpad, editor telemetry, or client-private
reasoning may be requested or stored. HydraMem receives only the final text
needed by the existing verifier/parser.

## Where it acts in HydraMem

The bridge would affect only the LLM provider layer:

| HydraMem component | Current provider path | With bridge |
|--------------------|-----------------------|-------------|
| `VoGVerifier` | `OllamaProvider` or configured external provider | `ClientLLMProvider` if enabled |
| `RelationInferrer` | `gardener_infer_with` provider | `ClientLLMProvider` if selected |
| `ConflictChecker` | `create_provider(config)` | `ClientLLMProvider` if selected |
| `SearchService` vector/BFS/PPR path | no LLM required until chunk VoG | unchanged except VoG provider |
| Ingestion chunking/entity extraction | no LLM by default | unchanged |

The bridge should not change storage, search ranking, session persistence, or
telemetry semantics.

## Risks

- **False assumption that Copilot is callable.** VS Code Copilot is not a
  generic localhost LLM endpoint. A bridge requires an explicit extension or
  sidecar with user consent.
- **Privacy ambiguity.** A client model may be cloud-hosted. HydraMem must make
  this visible in config/docs and keep the default local-first behaviour.
- **Prompt leakage.** VoG prompts include snippets from the local knowledge
  base. Sending them to a client-side cloud model must be an explicit opt-in.
- **Deadlocks / re-entrancy.** If the same agent call blocks waiting for a
  model that is itself waiting on HydraMem, the adapter can hang. Use a simple
  request/response endpoint and strict timeouts.
- **Provider drift.** Client APIs can change faster than HydraMem releases.
  Keep the core provider generic; put VS Code-specific code in an optional
  adapter package or example extension.
- **Policy violations.** Some client model APIs may prohibit proxying or
  automation. The adapter must respect the client's terms and permissions.

## Computational cost

- HydraMem overhead: one local HTTP request per LLM call.
- Latency: dominated by the client model; expect 100 ms to several seconds.
- Memory: negligible in HydraMem.
- Cost: charged according to the client/provider policy, not HydraMem.

## Privacy implications

Medium risk, opt-in only.

This feature can preserve HydraMem's local storage guarantees, but it may send
verification prompts and source snippets to the client-hosted model. That model
could be local, enterprise-hosted, or cloud-hosted. The config and telemetry
should label the active provider as `client` so users can audit when this path
was used.

The feature must preserve the existing **No CoT capture** rule: HydraMem does
not request, store, or infer the client's private chain-of-thought.

## Local-first viability

Mixed.

The core implementation can remain local-first because the bridge is disabled
by default and only talks to `localhost`. Whether the actual model call stays
local depends on the client-side adapter. For strict local-first deployments,
Ollama remains the recommended provider.

## Suggested implementation strategy

1. Add `hydramem/llm/client.py` implementing `ClientLLMProvider` with timeout,
   optional bearer token, and empty-string failure semantics.
2. Register `"client"` in `hydramem/llm/factory.py`.
3. Extend `Config` with `llm.client.endpoint`, `timeout_seconds`,
   `auth_token_env`, and `fallback_provider`.
4. Add a tiny fake adapter in tests that returns deterministic VoG responses.
5. Add an optional `examples/client-llm-bridge/` adapter skeleton rather than
   putting VS Code-specific code in the core package.
6. Document that VS Code Copilot requires an extension-side adapter; HydraMem
   cannot call Copilot directly through MCP alone.
7. Log `llm_preset=client` in telemetry and include bridge errors only as
   metadata, never prompt content.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/llm/client.py` | **NEW** — localhost/sidecar `ClientLLMProvider` |
| [`hydramem/llm/factory.py`](../../../hydramem/llm/factory.py) | Register `client` provider |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | Add `llm.client.*` config fields |
| [`config.yml.example`](../../../config.yml.example) | Document disabled client provider settings |
| [`hydramem/verification/pipeline.py`](../../../hydramem/verification/pipeline.py) | Ensure `vog_use_local_llm=false` respects `llm.provider=client` |
| [`hydramem/server.py`](../../../hydramem/server.py) | Telemetry should report `llm_preset=client` when active |
| `examples/client-llm-bridge/` | **NEW** — optional adapter skeleton |
| `tests/test_llm_client_provider.py` | Provider timeout/auth/failure tests |
| `tests/test_verification.py` | VoG with fake client provider |

## References

- VS Code Language Model API documentation
- Model Context Protocol host/server architecture
- HydraMem `LLMProvider` protocol in [`hydramem/llm/base.py`](../../../hydramem/llm/base.py)
- HydraMem no-CoT rule in [`../roadmap.md`](../../roadmap.md)