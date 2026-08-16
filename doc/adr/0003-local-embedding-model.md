# ADR 0003 — Local embedding model: `multilingual-e5-large` at 1024 dimensions

**Status:** Accepted · 16 August 2026
**Decider:** Parul Bhoite ("use something free")

## Context

No source document names an embedding model. The choice must be made in M0 because the pgvector column's dimension is fixed by the migration that creates it, and changing it later means re-embedding every chunk in every workspace.

Offered: Voyage `voyage-3` (paid), OpenAI `text-embedding-3-large` (paid), or a local model. **Decision: free, therefore local.**

## Decision

**`intfloat/multilingual-e5-large`, 1024 dimensions, served through `fastembed`.**

Runs in-process on CPU. No API key, no per-token cost, no third-party call.

### Why this model

- **1024 dimensions is deliberately the same as Voyage `voyage-3`.** If a paid provider is ever wanted for quality, the column dimension does not change and the migration is a re-embed, not a schema change. Choosing 384 or 768 today would foreclose that.
- **Multilingual, including Arabic.** Doc 01 §6 makes Arabic architecture-readiness an NFR and doc 02 puts Arabic on the roadmap. An English-only model would have to be replaced the moment that work starts — and replacing it means re-embedding everything.
- **Customer documents never leave the infrastructure.** Doc 01 §6 commits contractually that customer documents are not used to train third-party models, and the landing page states it. A local model makes that structurally true for the embedding path rather than contractually true.

### Why `fastembed` rather than `sentence-transformers`

`fastembed` runs ONNX via `onnxruntime` and does not pull in PyTorch — roughly 60 MB of dependency instead of well over 2 GB, which matters for a native (non-containerised) install per ADR 0001.

## Consequences

- **Indexing is CPU-bound and slower than a hosted API.** Acceptable at MVP document volumes; document ingestion is already an asynchronous background job, so latency lands on a job, never on a request.
- **First run downloads ~1.1 GB of model weights** to `/models/`, which is gitignored. This must be documented in the README as a first-run cost.
- `embedding_model_id` and `embedding_dim` are stored **on every chunk row**, so a future migration can identify what needs re-embedding without guessing, and two models can coexist during a transition.
- Retrieval quality is likely below `voyage-3`. Because this directly affects grounding quality, `/evals/grounding` (M8) should include retrieval-quality cases so a later swap can be justified with measurements rather than vibes.
- `multilingual-e5` requires `"query: "` and `"passage: "` prefixes. Getting this wrong silently degrades retrieval, so it is enforced in one place — the embedding service — never at call sites.

## Revisit when

Retrieval quality is measurably limiting, or Arabic generation ships and warrants a dedicated evaluation. Swapping to `voyage-3` is then a re-embed at unchanged dimensionality.
