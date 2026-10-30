# Licences and attribution — SN92 generalist decision data, train v1

Compilation licence: **CC-BY-4.0**. Per-item licence in the `licence` field: CC-BY-4.0 (107,379 items), CC0-1.0 (2,168).
Items derived from the sources below were adapted (re-worded, re-formatted to the REAX decision schema).

## Source datasets
* **CUAD** — The Atticus Project, "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review" (Hendrycks et al., 2021),
  CC-BY-4.0, https://huggingface.co/datasets/theatticusproject/cuad — 354 contract-entailment items (windows of public SEC
  EDGAR exhibits; company names and signatories are those of the public filings).
* **Wikidata** — CC0-1.0, https://www.wikidata.org — facts for closed-book / knowledge worlds (SPARQL queries pinned).
* **UCI Bike Sharing** (dataset 275) — CC-BY-4.0. Fanaee-T, H. and Gama, J. (2013), "Event labeling combining ensemble
  detectors and background knowledge", Progress in Artificial Intelligence — table / forecasting worlds.
* **OpenAlex** metadata — CC0-1.0, https://openalex.org — bibliographic worlds.
* Earlier SN92 specialist data (`lane = reuse`), published as `decisionmodels/sn92-specialists` (CC-BY-4.0).

## Models used to write or verify items
Recorded per item in `generator` / `verifiers`.
* Open-weight: Qwen3.5 / Qwen3.8 (Apache-2.0), Gemma 4 (Apache-2.0), DeepSeek V3.2 / V4 Flash (MIT), GLM-5.1 / 5.2 (MIT),
  Kimi K2.6 / K3 (modified MIT: Moonshot requires prominent "Kimi" attribution for very large commercial products).
* Proprietary: OpenAI GPT-6 Astra, GPT-6 Luna, GPT-6.1 Sol; Anthropic Claude (Claude Code). Their providers' terms
  restrict using outputs to develop competing models; users are responsible for complying with the terms that apply to
  their own use.

## Benchmarks
Benchmark corpora (HF Decision Index public suites, AA Decision Index public components, JevBench public items and
related public sets) were used only to screen this data and to measure aggregate structure. No benchmark item was given
to a generator. Items derived from CLINC150, BANKING77 and MASSIVE were removed from this release.
