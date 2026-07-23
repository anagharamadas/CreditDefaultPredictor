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
