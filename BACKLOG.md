# Backlog — parked, deliberately

Items here are legitimate extensions that are out of v1 scope by charter decision
(CHARTER.md §5). None may start before P11 is demonstrably working.

1. **NLP features from `desc` / `title` / `emp_title`.** Text-derived risk signal; the
   Zenodo curators' related work legitimises the idea. Revisit only with the leakage
   question answered (is the text as-submitted at application time?).
2. **Reject inference using `rejected_2007_to_2018Q4.csv`.** 27.6M rejected applications
   enable measuring (and partially correcting) the funded-loans-only selection bias.
   Requires resolving what `Risk_Score` actually is first.
3. **Survival-analysis framing.** Time-to-default modelling would use the censored
   (Current) loans and the 60-month book honestly. Most correct framing, hardest to
   serve; candidate for v2.
4. **60-month loan support.** Requires the survival framing or a fixed-horizon label;
   the v1 matured-vintages policy cannot cover them.
5. **Cloud demo deployment.** Short-lived, tear-down scripted, within the $20 ceiling.
   Decision deferred to P8 per charter.
8. **A small demo page for the P12 recruiter walkthrough.** A single static page
   (one HTML file served by the API, or a tiny Streamlit app) with a pre-filled
   loan application, a Score button, and the response shown as a decision plus the
   threshold and the assumed cost ratio it rests on. FastAPI's auto-generated
   `/docs` already gives an interactive form for anyone technical, so this is
   purely for the non-technical five-minute demo — it must not grow into a loan
   officer console (Charter §5 non-goals). Do it only after P12's demo path exists
   and shows a real need.
7. **Slim the serving image with `mlflow-skinny`.** The API image is ~1.8 GB,
   dominated by the full `mlflow` package pulled in for its *client*. Our code
   never runs a tracking server (the compose service uses the official image), so
   the skinny client would likely suffice. Deferred because it is a project-wide
   dependency change (training and registry code use the same package) for a
   benefit — image size — that no stated constraint currently requires. Revisit if
   the P8 deploy-target decision lands somewhere size-sensitive.
6. **Research the FN:FP cost ratio (review ADR-0003).** — GitHub issue #70; the one
   backlog item with a deadline (before the P6 retro). ADR-0003's 5:1 ratio is
   order-of-magnitude reasoning, not evidence; the operating threshold is fully
   determined by it. Research LGD/recovery rates for unsecured US personal loans and
   margin structure, then either confirm the ADR or supersede it with a sourced ratio.
   Owner: Anagha (research, not implementation).
