# 08 — Embeddings, pgvector, and hybrid scene search

Code: `services/api/routes/search.py`, `stage_index` in `services/worker/pipeline.py`.

## What we embed
For each scene, `search_text` is the vision description, plus the tags, plus the transcript spoken during the scene. `gemini-embedding-001` turns that text into a 768-dimensional vector, and texts with similar meaning land close together.
- **Task types.** Documents are embedded with `RETRIEVAL_DOCUMENT` and queries with `RETRIEVAL_QUERY`. The model is trained for this asymmetry ("short question" vs "long passage").
- **Matryoshka dims.** The model natively outputs 3072 dims, and truncating to 768 keeps most of the quality. pgvector's HNSW index supports at most 2000 dims.
- **Versioning.** `scenes.embedding_model` records which model made each vector. Vectors from different models must never be compared.

## Two retrievers, one ranking
| | Keyword (Postgres FTS) | Semantic (pgvector) |
|---|---|---|
| Matches | exact words (stemmed: "transcribing" ≈ "transcription") | meaning ("scientist explaining" ≈ "man in glasses talking about Europa") |
| Fails on | synonyms, paraphrase | rare names, exact phrases, numbers |
| Query | `search_tsv @@ websearch_to_tsquery('english', q)` ranked by `ts_rank_cd` | `ORDER BY embedding <=> query_vec` (cosine distance) |

**Reciprocal Rank Fusion** merges the two lists without comparing their scores, which live on different scales:
`score(scene) = Σ over lists 1 / (60 + rank_in_that_list)`.
A scene ranked well by both retrievers rises to the top. The API returns `matched_by` so you can see which retriever found each hit.

## HNSW in one paragraph
An exact nearest-neighbour search compares the query with every vector. HNSW builds a layered "small world" graph and walks it greedily, giving *approximate* results in roughly logarithmic time. At our scale (hundreds of scenes) an exact scan would also be fine. The index is there for when the benchmark grows.

## Try this
1. `curl "localhost:8010/projects/<pid>/search?q=moon&mode=keyword"`, then the same with `mode=semantic`, then `mode=hybrid`. Compare the results.
2. Search for something never said but visible, such as "calendar" or "black screen with white text". Only semantic search (via the descriptions) can find it.
3. In psql: `select index, embedding <=> (select embedding from scenes where index=0 limit 1) d from scenes order by d limit 5;` finds the scenes most similar to scene 0.

## Results on the three NASA clips (60 scenes)
| Query | Top hits | Found by |
|---|---|---|
| `moon` | supermoon close-ups and the full-moon graphic | keyword + semantic |
| `calendar dates` | the animated calendar (supermoon 8.5–27.9 s) | **semantic only**: `websearch_to_tsquery` ANDs the words, and "dates" appears nowhere |
| `scientist explaining the mission` | all three interview answers | **semantic only**: the word "scientist" never appears |
| `lightning on Jupiter` | the lightning clip's Jupiter shots | keyword + semantic |

Known limitation: semantic search always returns *k* results, even weak ones (the 2nd and 3rd hits for "calendar dates" are unrelated). A distance cut-off or a re-ranker can come later, if the editing agent needs one.
