# Anti-Patterns: Things HydraMem Will Not Do 🔴

> **Status:** Documented to be explicit
> **Owner:** project leads

This document exists because the surrounding research literature is full
of features that *sound* attractive but would **destroy HydraMem's core
value proposition**. Each item below has been considered and rejected
with a concrete reason. Adding any of them requires explicit consensus
from project leads and a redefinition of the privacy / honesty contract.

---

## 1. Federated Gradient Sharing Across Tenants

**The pitch.** Multiple HydraMem instances send model gradients
(embedding adapter, GNN scorer, SR-MKG weights) to a coordinator that
averages them — "decentralised learning, no raw data shared!".

**Why we won't.**

- Gradient inversion attacks (Zhu et al., *Deep Leakage from Gradients*,
  NeurIPS 2019; Geiping et al., 2020) reconstruct training samples from
  gradients with disturbing fidelity, especially in small-batch regimes
  typical of personal corpora.
- Differential privacy that would actually defeat these attacks
  destroys utility at small scale.
- The complexity of correct FL (heterogeneity, communication, drift,
  Byzantine fault tolerance, signed update verification) **doubles the
  surface area** of the project.
- Real benefit for a typical user (1 machine, 1 corpus) is near zero.

**The supported alternative**: signed export/import of *verified
knowledge subgraphs* with HMAC envelopes. Already shipped. That is the
correct unit of federation for this project.

---

## 2. Capturing the Agent's Chain-of-Thought

**The pitch.** "If we capture the agent's reasoning trace verbatim we
can build a reasoning-trajectory model and become amazing!"

**Why we won't.**

- HydraMem's central trust signal is "**we never see your prompts'
  internal reasoning**". Breaking that is unrecoverable.
- The legitimate substitute is reasoning **motifs** over public graph
  nodes — see [reasoning-motifs.md](reasoning-motifs.md).
- Anything beyond that abstraction belongs in a different product
  category.

**Hard rule.** Sessions store only the user query and the grounded
context HydraMem returned. CI must include an assertion that the
session schema contains no free-text field corresponding to client
internals.

---

## 3. Full-Attention Graph Transformers in the Default Install

**The pitch.** "Graph Transformers (GraphGPS, NodeFormer, Polynormer)
are SOTA on long-range graph reasoning, let's adopt one."

**Why we won't (in defaults).**

- Memory cost is O(N²) for full attention or O(N · M) with samplers and
  the sampler logic itself is heavy.
- Local-first contract → assume consumer hardware. Even small models
  push 4–8 GB resident memory.
- The marginal accuracy gain over R-GCN with Laplacian PE on the graph
  sizes HydraMem actually sees is small.

**What we'll do instead.** Cap GNN backends at relational message
passing (R-GCN / CompGCN) with Laplacian PE features. A research branch
may explore GT later, but it must never be the default.

---

## 4. Reinforcement Learning of Retrieval Policy without a Benchmark

**The pitch.** "Train a policy network with success/failure rewards on
retrieval to learn the optimal traversal strategy!"

**Why we won't (yet).**

- "Success" is undefined without a reproducible benchmark. The roadmap
  already commits to MuSiQue + LongMemEval — those numbers must exist
  *first*.
- Without ground truth, any reward signal we invent will be a
  self-referential loop that consolidates whatever the system already
  does well.
- RL pipelines are infamously brittle. A 5 kLOC project should not own
  one until the benchmark harness can detect regressions.

**Sequencing rule.** Adaptive retrieval planning (zero-shot or
LLM-classifier) ships first. Calibration of weights via supervised
learning ships second. RL only after a stable benchmark exists and
shows specific gaps that supervised methods cannot close.

---

## 5. "Agent That Answers For You"

**The pitch.** "Bundle a chat agent so users can talk to HydraMem."

**Why we won't.**

- HydraMem is **memory**, not a chat product. The MCP design exists
  precisely so different agents can plug in without HydraMem caring.
- Adding a built-in agent would create a worse copy of OpenCode / Claude
  Desktop / Cursor while diluting maintenance focus.

---

## 6. Hosted SaaS in This Repository

**The pitch.** "Add a managed-cloud option in the same repo."

**Why we won't.**

- Local-first is a contract, not a slogan. Mixing cloud code paths into
  the open-source core invites configuration mistakes that exfiltrate
  user data.
- A separate `hydramem-cloud` repository is acceptable. The OSS core
  stays local-first.

---

## 7. Telemetry That Leaves the Machine Without Per-Event Opt-In

**The pitch.** "Anonymous aggregates would help us understand usage."

**Why we won't (silently).**

- Even aggregate metrics can fingerprint usage patterns.
- The supported model is the existing `hydramem telemetry --opt-in`
  flag with **per-event** decisions and explicit user awareness.

---

## 8. Hardcoded Schema for the Knowledge Graph

**The pitch.** "Predefine entity/relation types globally."

**Why we won't.**

- Each user's domain is different. A locked schema kills the value of
  ontology induction.
- The supported direction is bottom-up induction — see future docs on
  hyper-relational schema and (later) ontology induction.

---

## Summary table

| Anti-pattern | Reason | Supported alternative |
|---|---|---|
| Federated gradients | Privacy / complexity | Signed knowledge export |
| CoT capture | Trust contract | Reasoning motifs |
| Default Graph Transformers | RAM / CPU cost | R-GCN + LPE |
| RL retrieval policy | No benchmark yet | Zero-shot / supervised planner |
| Built-in chat agent | Out of scope | MCP integration |
| Hosted SaaS in core | Local-first contract | Separate repo |
| Silent telemetry | Privacy contract | Explicit per-event opt-in |
| Hardcoded schema | Domain rigidity | Bottom-up ontology induction |
