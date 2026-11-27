# RAG comparison audit — 23 September 2026

Owner: Krishna Malhotra

Source result: `evaluation/rag_comparison_results_v1.json`

SHA-256: `f53b08a6916172ce537019f8bb0d4a9538b9dbe0e5983d8eda7e81026ec732c7`

## Mechanical results

- 21 of 21 RAG generations were valid JSON.
- No output invented a provision ID or selected an ID outside the retrieved top eight.
- RAG changed 17 of 21 answers.
- Five RAG answers failed the release gate: TEST_005, TEST_008, TEST_009,
  TEST_015 and TEST_017.
- Two answers selected the sole provision whose local legal status remains uncertain.
- One answer selected a civil-penalty provision as the complaint provision.
- LoRA-only returned three out-of-scope decisions; RAG returned none.

These checks measure schema and gate compliance. They do not establish legal accuracy.

## Research review

### Clearly improved

- TEST_001: RAG changed snatching (BNS 304) to general theft (BNS 303).
- TEST_013: RAG preserved insufficient information and identified the relevant
  distinctions among IT Act sections 66, 66C and 66D.

### Preserved reasonable behavior

- TEST_002, TEST_003, TEST_011, TEST_012 and TEST_016.

### Unchanged unresolved issue

- TEST_004 still selects BNS 78 without the complaint stating the victim fact
  required by the provision.

### Mixed or blocked by the release gate

- TEST_005 and TEST_009 selected IT Act 66E, whose local status is uncertain and
  which is not recommendation-approved.
- TEST_008 moved toward unauthorized-access facts but selected section 43, a
  civil-penalty provision, instead of treating it as context for section 66.
- TEST_017 identified the extortion provision but dropped criminal intimidation
  and selected a section that is not recommendation-approved.

### Regressions

- TEST_006: bank personation changed from IT Act 66D to the less direct section 66.
- TEST_007: online personation changed from section 66D to section 66C without a
  stated use of a password, signature or other unique identification feature.
- TEST_010: retrieval missed BNS 318 and the answer focused on unrelated IT Act 66B.
- TEST_014: the missing-information candidate changed from ordinary hurt to
  grievous hurt despite the injury type being unknown.
- TEST_015: entrusted-property facts changed from criminal breach of trust to
  dishonest misappropriation even though BNS 316 was retrieved.
- TEST_018: RAG dropped IT Act 66D from a completed online-personation scenario.
- TEST_019, TEST_020 and TEST_021 changed correct out-of-scope decisions into
  speculative insufficient-information answers.

## Root causes

1. Retrieval always returns candidates even when the complaint is noncriminal.
2. Keyword anchors do not understand negation. TEST_021 says there were no threats
   or forged documents, yet those words triggered extortion and forgery candidates.
3. TEST_010 lacks an ordinary-language commerce-to-cheating retrieval bridge.
4. The single generation prompt encourages the model to choose something from the
   supplied candidates, even when none applies.
5. The LoRA often selects one familiar section and does not reliably compare every
   retrieved provision's material requirements.
6. Recommendation status was enforced after generation, so five answers were
   correctly blocked but remained unusable as displayed suggestions.

## Decision

Do not use RAG v1 as the final inference path and do not retrain yet. The retrieved
candidate pool is useful, but the decision stage needs redesign.

## Required RAG v2 flow

1. Run the trained LoRA's original triage first. Preserve a confident out-of-scope
   outcome unless new stated facts justify reopening it.
2. Apply negation-aware retrieval and a minimum relevance threshold. Allow retrieval
   to return no candidates.
3. Separate contextual provisions from recommendation candidates.
4. Evaluate each candidate independently as supported, missing facts, or rejected.
5. Assemble the final JSON in code from those per-candidate decisions.
6. Enforce in-force, offence-kind and recommendation gates before display.
7. Compare LoRA-only, RAG v1 and RAG v2 against reviewed reference labels before
   deciding whether targeted LoRA v2 training is necessary.
