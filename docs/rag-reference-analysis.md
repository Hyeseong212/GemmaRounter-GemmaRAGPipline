# RAG Reference Analysis

This note summarizes what the current [`RAG-reference-scripts`](/home/rb/AI/RAG-reference-scripts) folder already does and how the router should use it.

## Current Structure

- [app.py](/home/rb/AI/RAG-reference-scripts/app.py)
- [ingest.py](/home/rb/AI/RAG-reference-scripts/ingest.py)
- [check_db.py](/home/rb/AI/RAG-reference-scripts/check_db.py)
- [check_qdrant.py](/home/rb/AI/RAG-reference-scripts/check_qdrant.py)

## What It Already Implements

### 1. Ingestion

[ingest.py](/home/rb/AI/RAG-reference-scripts/ingest.py) does this:

- loads documents from a target directory
- chunks them with `SentenceSplitter`
- embeds them with `BAAI/bge-m3`
- stores them in Qdrant collection `medical_knowledge`

Important detail:

- every ingest currently deletes and rebuilds the collection

So this is a rebuild-style pipeline, not incremental sync yet.

### 2. Retrieval + Answer API

[app.py](/home/rb/AI/RAG-reference-scripts/app.py) does this:

- connects to Qdrant `medical_knowledge`
- builds a LlamaIndex query engine with `similarity_top_k=2`
- sends the final prompt to a custom C++ server wrapper
- exposes `POST /ask`

Current API contract:

```json
{
  "question": "string"
}
```

Current response contract:

```json
{
  "answer": "string"
}
```

It also appends simple source strings like file name and page number to the final answer text.

### 3. Health / Count Scripts

[check_db.py](/home/rb/AI/RAG-reference-scripts/check_db.py) and [check_qdrant.py](/home/rb/AI/RAG-reference-scripts/check_qdrant.py) just inspect collection point counts.

## Architecture Reading

This folder is not a full end-to-end orchestration layer yet.

It is best understood as:

- a server-side grounded reference answerer
- backed by Qdrant
- using BGE-M3 embeddings
- using a custom LLM endpoint for final synthesis

So the missing front door is exactly the router:

- does the question need grounded reference lookup?
- if not, can local LLM answer within 20 Korean characters?
- if not, should the server large model answer without RAG?

## Strong Points

- clear ingest and query separation
- simple API surface
- already grounded on vector retrieval
- already returns source hints

## Current Gaps

### 1. Very fixed assumptions

- fixed collection name: `medical_knowledge`
- fixed Qdrant host: `localhost:6333`
- fixed LLM endpoint: `http://localhost:8080/infer`
- fixed GPU placement in code

### 2. No front-door routing

The API assumes every incoming question should go through RAG.

That means:

- general questions waste retrieval
- non-grounded questions are not separated from grounded questions
- server large-model only questions are not distinguished

### 3. No structured retrieval result contract

The answer is returned as one combined text blob with appended source lines.

It does not return:

- retrieved chunk ids
- confidence or score summaries
- structured citations
- retrieval miss reasons

### 4. Rebuild-only ingestion

The collection is deleted and rebuilt on ingest.

That is okay for a prototype, but not ideal for production updates.

## Router Recommendation

The router should treat this pipeline as only one downstream path:

- `server_rag`

Use it when:

- manuals or SOPs must be referenced
- error code meaning must be grounded
- procedure or device usage answer should come from stored docs

Do not use it when:

- the question is just a short general question
- the expected answer should stay within 20 Korean characters
- the question is general but needs broader reasoning instead of document lookup
- the request should stay local for latency

## Recommended Handoff Contract

When the router chooses `server_rag`, pass:

- target system: `rag_reference_api`
- endpoint: `POST /ask`
- request body: `{"question": user_message}`

## Bottom Line

`RAG-reference-scripts` is already a usable grounded reference service.

What it was missing was not retrieval itself, but the routing layer above it.

That is why the next correct step is:

1. separate general vs grounded questions
2. use `server_rag` only for grounded reference questions
3. split general questions into `local_llm` vs `server_llm`
