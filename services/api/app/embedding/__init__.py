"""The embedding boundary.

Nothing outside this package knows which model turns text into a vector, and
nothing outside it applies a model's prompt prefixes. Two reasons, and the
second is the one that bites:

**A model swap must be a registry change.** `embedding_model_id` and
`embedding_dim` are stored on every chunk row (ADR 0003) precisely so a future
provider can be introduced without guessing what needs re-embedding. That is
only true if one place decides which provider runs.

**`multilingual-e5` requires `query: ` and `passage: ` prefixes, and getting it
wrong fails silently.** Retrieval still returns rows; they are just worse, by an
amount nobody notices until grounding quality is measured. ADR 0003 requires the
prefixes be applied in the embedding service and never at a call site, so the
interface exposes `embed_passages` and `embed_query` rather than one `embed`.
There is deliberately no way to ask this package to embed unprefixed text.
"""
