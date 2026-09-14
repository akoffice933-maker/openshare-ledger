# Contribution Ledger — MVP

Open infrastructure for verifiable contribution attribution in **community-trained AI**.

Git is the source of truth. Contributions are scored only against measurable work, and history is stored as an append-only SHA-256 hash chain that is public and replayable from git. No external infrastructure, no trust required: anyone can recompute the chain and verify the result.

```
git history → validators → scoring → append-only ledger → snapshot + anchor
```

The hash chain exists for exactly one reason: so that **history cannot be rewritten retroactively**. Nothing external is required — the chain replays from git.

Ledger MVP is built and self-tested: **10 entries, 1,498.42 points, chain verified, 16/16 guarantees confirmed.**

Русская версия: [`README.ru.md`](README.ru.md)

---

## Quick start

```bash
cd openshare-ledger

# 1. state directory structure
python3 -m ledger init

# 2. register the private held-out set (never enters the repository)
python3 -m ledger heldout --file private/golden.jsonl

# 3. build a demo repository with a contribution history
python3 tools/make_demo_repo.py

# 4. see what is visible in git
python3 -m ledger collect --repo demo/repo

# 5. score points, take a snapshot, fix the anchor, build the report
python3 -m ledger score --repo demo/repo --cycle 2026-09

# 6. verify the chain and reproducibility of scoring
python3 -m ledger verify --repo demo/repo --recompute --cycle 2026-09

# 7. verify the guarantees
python3 -m ledger selftest
```

Output: `state/entries.jsonl`, `state/snapshots/2026-09.json`, `state/anchors.log`, `report.html`.

---

## What the demo data produces

| Contributor | Contribution | Points | Note |
|---|---|---:|---|
| Sofia Marin | 3 confirmed defects in the eval set | 750.00 | 4th defect unconfirmed — not paid |
| Ivan Petrov | 48 GPU-hours at 0.92 utilization | 529.92 | second proof at utilization 1.4 rejected |
| Dmitri Volkov | fine-tuning, delta +0.021 | 84.00 | "improvement" not measured on held-out — rejected |
| Elena Novak | 180 lines of code + 90 lines of docs | 76.50 | subjective category |
| Anna Kowalski | 40 + 18 data records | 58.00 | 5 duplicates, 3 contaminations, 4 PII records filtered from the second batch |
| Spam Bot | 200 exact duplicates | 0.00 | sybil dump zeroed by deduplication |

**Total: 1,498.42 points, 10 entries, chain intact, recomputation from git produces the same result.**

---

## Architecture

| Module | Responsibility |
|---|---|
| `ledger/collectors.py` | Reads git history, classifies files by path, extracts payload. A `Contribution-Type:` trailer in the commit message overrides classification |
| `ledger/validators.py` | Automated checks: deduplication, contamination, PII, schema, held-out set hash, harness version, physical plausibility of compute proofs |
| `ledger/scoring.py` | Formulas, splitting the budget into measurable and subjective parts, scaling to budget, project cap |
| `ledger/store.py` | Append-only store with hash chain, integrity check, aggregates |
| `ledger/snapshot.py` | Monthly snapshot: shares, totals, configuration hash |
| `ledger/anchor.py` | RFC 3161: builds a TimeStampReq, sends it to a TSA, stores the token, verifies the signature |
| `ledger/report.py` | HTML report with no external dependencies |
| `ledger/selftest.py` | Verifies the guarantees — economic and cryptographic |
| `ledger/cli.py` | Command line |

### Entry format

```json
{"seq":0,"ts":"2026-08-05T10:00:00+00:00","kind":"contribution",
 "data":{...,"points":63.0,"metrics":{...}},"prev":"000…0","hash":"9f2c…"}
```

`hash` is computed over the canonical JSON of `seq, ts, kind, data, prev`. Editing any entry breaks every subsequent one — checked immediately.

---

## Scoring rules

| Contribution type | Formula | Checks before scoring |
|---|---|---|
| Data | `accepted × k_data × novelty` | dedup, held-out contamination, PII, schema |
| Model | `max(0, delta) × k_model` | `dataset_hash` matches held-out, harness version |
| Evaluation | `confirmed defects × k_eval` | requires `confirmed: true` |
| Compute | `GPU-hours × k_compute × utilization` | utilization in (0, 1], `result_hash` present, proof limit |
| Code / docs | `lines added × k_code / k_docs` | **capped at 15% of the cycle budget** |

**Economics:** the cycle budget decays 15% every 6 cycles; the overall cap is fixed in the config before the first scoring run. If contributions exceed what the budget can hold, payouts scale proportionally — but the subjective part is always confined to its own share.

All coefficients live in `config.json`. Demo values are **placeholders** and need calibration against a real domain: right now, finding a defect in the eval set outweighs 48 GPU-hours, and that needs to be consciously confirmed or changed.

---

## Guarantees (verified by `selftest`)

```
✅ Duplicates are not paid                    ✅ Cycle budget is never exceeded
✅ Resubmission is not paid                   ✅ Subjective contribution is capped by share
✅ Test set contamination is blocked          ✅ Measurable work takes the larger share
✅ Personal data is filtered out              ✅ Emission decays over time
✅ "Improvement" off the held-out is rejected ✅ Whole chain passes verification
✅ Impossible compute proof is rejected       ✅ Retroactive editing is detected
✅ Negative delta is not paid                 ✅ Entry deletion is detected
✅ Scoring is deterministic                   ✅ Project cap limits issuance
```

---

## Deliberately not done in the MVP

An honest list, so a stub is not mistaken for a finished system:

| Not done | Why | What is needed |
|---|---|---|
| Real anchor publication | **Done** | DigiCert TSA, verified against system root CAs — `ledger verify --anchors` |
| Dispute procedure | Requires roles and notifications | Issue template + an `adjustment` entry in the ledger |
| Signed commits | Demo repository has no GPG | Check `git verify-commit` in the collector |
| Multiple repositories | One project, one ledger | Config with a list of repositories |
| Payout export | No legal entity, no revenue | After Phase 3: export in accounting format + KYC |
| Web interface | Not the bottleneck | Read `snapshots/*.json`; the report is already generated |

---

## Next

In order of importance:

1. **Signed commits** — otherwise attribution rests on the author field, which is forged with one line.
2. ~~**Real anchoring**~~ — **done**: DigiCert TSA, `snapshot --anchor --publish`. Verified with `verify --anchors`; needs no file from this repository. Sigstore Rekor remains an option for inclusion proofs.
3. **Dispute procedure** — 14 days to contest; the decision is published as a ledger entry.
4. **Weight calibration** against the chosen domain: currently placeholders.
5. **Compute proof by re-run** — deterministic re-execution rather than trust in `result_hash`.

---

## The reminder worth keeping in view

> Points have no monetary value, are not transferable, and do not entitle anyone to payment.
> A reward mechanism will be introduced separately — together with a legal structure and revenue.

This is not a formality. It is what keeps the whole construction outside securities regulation.

---

## License

MIT — see [`LICENSE`](LICENSE).
