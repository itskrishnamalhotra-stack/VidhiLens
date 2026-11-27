# NyayaSetu Live Product Acceptance Report

**Test date:** 28 September 2026  
**System tested:** Firebase frontend connected to the active Colab vLLM, LoRA, RAG, FastAPI and Cloudflare demo backend  
**Result:** PASS — 29 of 29 acceptance checks passed

## Functional results

| Scenario | Result |
|---|---|
| Greeting | Returned a conversational response without running legal analysis; title remained `New complaint` |
| Help question | Explained the intake process without suggesting legal provisions |
| Clear theft | Identified BNS 303 and offered a complaint draft |
| Vague missing phone report | Returned insufficient information and asked for the missing theft fact |
| OTP and fake bank officer fraud | Identified IT Act 66D, BNS 319 and IT Act 66C |
| Password and account misuse | Identified IT Act 66C |
| Weather question | Correctly returned out of scope with no provision |
| Death threat messages | Identified BNS 351 |

Every positive result contained reviewed legal text and an official source URL. No unsupported provision ID appeared.

## Complaint workflow

- Created a draft only after a positive supported analysis.
- Edited location and evidence.
- Required provision reanalysis after legally relevant evidence changed.
- Confirmed the rechecked version as a local NyayaSetu record.
- Clearly stated that saving does not create an FIR or government submission.
- Verified saved-draft persistence, cancellation and deletion.

## Security and multi-user behaviour

- Requests without a token were rejected.
- An incorrect token was rejected.
- A second demo user could not read another user's session.
- The owner could read the same session.
- Conversation history survived a browser refresh.

## Performance

- Eight concurrent scenario requests completed in **29.771 seconds** wall time.
- Six requests used the model pipeline.
- Model request latency: **3.757 seconds minimum**, **13.938 seconds median**, **26.910 seconds maximum**.
- Greetings and help responses completed in under **0.5 seconds** at the API.

## Frontend checks

- Desktop chat, source expansion, draft editing and confirmation were exercised through the deployed Firebase interface.
- The 390 px mobile layout had no horizontal overflow.
- The application produced no site-origin console errors during the test.
- Browser-extension overlays such as Grammarly or a floating robot are external to NyayaSetu.

## Acceptance decision

The current build meets the acceptance standard for a university demonstration and research prototype. Its outputs remain research guidance based on AI-reviewed labels. It must not be presented as lawyer-verified legal advice or as an official complaint-filing service.
