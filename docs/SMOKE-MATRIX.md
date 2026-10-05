# Release smoke matrix (0.2.0)

Live checks run for the 0.2.0 release on 2026-10-05, on the development machine: Windows 10, Python 3.13.6, NVIDIA GPU,
a local Ollama with `nomic-embed-text:latest`, `qwen2.5:0.5b`, `qwen3.5:4b` and the other eval models, and chromadb
1.3.5. Timings are evidence about this machine, not pass or fail; nothing is gated on them. Every run used a throwaway
temporary directory, never the real `runtime/`.

## Full suite from a fresh clone

`git clone --branch t6-release` of the release commit into a temporary directory, then:

| Run | Command | Result |
|---|---|---|
| with chromadb (system Python, chromadb 1.3.5 installed) | `python -B -m unittest discover -s tests` | FRESH_WITH |
| without chromadb (a new `python -m venv` with nothing installed; `import chromadb` fails) | `<venv>\Scripts\python -B -m unittest discover -s tests` | FRESH_WITHOUT |

Skipped with chromadb: the two blocker checks in `tests/test_support_blocker.py` that only run under
`AGENT_HARNESS_BLOCK_MODULES=chromadb`. Skipped without chromadb: those two, the "chromadb importable" check in the
same file, and the real-Chroma ordering test in `tests/test_store_contract.py`.

## Document + Question, a real message in the browser

A throwaway server (temporary runtime, `num_ctx` 2048, reply limit 256, memory off) was opened in a browser. The
**Document** button opened the Document box; a 10,871-character document (150 routine archive lines with
"The vault code word is PELICAN." in the middle) went in the Document box, "What is the vault code word?" was typed in
the question box, and Send was pressed.

| Check | Result |
|---|---|
| Message the server recorded | 10,910 characters, ending `\nQuestion: What is the vault code word?` (composed in the browser) |
| Reply from `qwen3.5:4b` | "The vault code word is **PELICAN**." |
| Context meter | about 207 of 1,587 tokens |
| Derived context block | shown collapsed: "extractive_map_reduce v2, depth 1, 4 source spans"; expanded, it showed the head lines, the marker, the PELICAN line, the tail lines and the question, with ranges 0-212, 5390-5421, 10653-10871, 10872-10910 |
| Composition recorded | `small_ends` |
| `verify_derived(original, derived)` on the record fetched from the API | `[]` (ranges, hash and text agree) |

Earlier, during T5, the same fields were checked for their error paths (a document with no question; more than 20,000
characters) and at a 375 px phone width.

## Conversation memory: the three conditions

`python -B -m tests.live_memory_probe` seeds four turns, lets the catch-up finish, and retrieves "Where do I live?".

| Condition | Command | state | store | tier | reason / fix | retrieved by | top hit |
|---|---|---|---|---|---|---|---|
| Chroma importable, model present | `python -B -m tests.live_memory_probe` | ready | chroma | vector | none | vector | "Your home is in Cedar Rapids." |
| chromadb blocked, model present | `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m tests.live_memory_probe` | ready | sqlite | vector | none | vector | "Your home is in Cedar Rapids." |
| embedding model unavailable | `python -B -m tests.live_memory_probe --model no-such-embed-model` | ready | chroma | lexical | `embedding_model_missing` / `run: ollama pull no-such-embed-model` | lexical | "Where is my home?" |
| both: chromadb blocked and model unavailable | `AGENT_HARNESS_BLOCK_MODULES=chromadb python -B -m tests.live_memory_probe --model no-such-embed-model` | ready | sqlite | lexical | `embedding_model_missing` / same fix | lexical | "Where is my home?" |

Keyword rows indexed were 4 of 4 in every condition; vector rows 4 of 4 when the model was present and 0 when not.

## Startup catch-up: `--backlog 800`

`python -B -m tests.live_memory_probe --backlog 800` seeds 800 turns, starts the server-side catch-up, and retrieves
"What is the home number?" about 0.5 s later.

| retrieve() during catch-up | served by | indexed when asked | whole catch-up | afterwards |
|---|---|---|---|---|
| 0.226 s | vector (a partial index) | 96 of 800 vectors, 800 of 800 keyword rows | 7.35 s | tier vector, state ready, served by vector |

Earlier runs of the same command: 0.003 s served by the keyword tier with 0 vectors indexed at 0.5 s (400 turns, T4);
the reviewer measured 0.00 s, keyword-served (800 turns). Which tier answers during catch-up depends on how far the first
embedding batch has got; in no run did retrieval wait for the catch-up.

## Overflow smoke: one oversized message end to end

`python -B tests/ollama_overflow_smoke.py MODEL` sends the three-fact document (opening COBALT, hidden VIOLET, closing
MARIGOLD) at `num_ctx` 2048 and asks for the hidden marker.

| Model | Raw request | Reply state | Answer | Prompt tokens | Derived depth | All three facts in derived text | Script exit |
|---|---|---|---|---|---|---|---|
| `qwen3.5:4b` | `context_exceeded` | done | "The hidden project marker is VIOLET." | 415 | 1 | yes | 0 |
| `qwen2.5:0.5b` | `context_exceeded` | done | "COBALT." (wrong) | 209 | 1 | yes | 1 |

The 0.5B result is a silent wrong answer: extraction put the right sentence in front of the model, and the model
answered with a different fact. The T1 run of this smoke (with the old 10% head and tail) got VIOLET from the same
model. It is consistent with the eval: below 4B the final answer is not reliable.

## Eval summary

From [EVAL-RESULTS.md](EVAL-RESULTS.md) (120 runs: 5 models x 3 compositions x 8 fixtures, one run each, temperature 0):

- Winner by the pre-declared rule: `small_ends`, on a near-tie (thresholds met 2 / correct 33 / extraction passes 34,
  against `baseline` 2 / 32 / 33 and `block_by_question` 2 / 33 / 33).
- Met: final-answer correctness 8/8 for `qwen3.5:4b` and `qwen3.5:9b`; the absent-fact fixture failed visibly for every
  model in every composition.
- Missed, recorded as named limitations: answer passage in the derived text for 100% of fixtures with models of 1.5B and
  up (`qwen2.5:1.5b` and `qwen3.5:2b` 7/8), and 7/8 for 0.5B (4/8).
- Silent wrong answers under the default: four of 40 runs, all with the 0.5B and 2B models.
