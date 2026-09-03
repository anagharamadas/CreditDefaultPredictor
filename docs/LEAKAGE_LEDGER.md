# Leakage Ledger — all 151 raw columns, classified

GENERATED from `src/credit_default/ledger.py` by `scripts/render_ledger.py` — the
code is the authority (the P4 feature allowlist imports it); edit there, rerun here.

Classification question for every column: *could a loan officer have seen this
value at the second the application was submitted — and is it the borrower's
information rather than LendingClub's own assessment of them?*

| Category | Count |
|---|---|
| FEATURE | 79 |
| BANNED_POST | 38 |
| BANNED_UNDERWRITING | 4 |
| TARGET | 1 |
| METADATA | 5 |
| UNDECIDED | 24 |
| **total** | **151** |

> **24 columns UNDECIDED** (first-pass state, ticket #18). Ticket #21 must resolve every one; P2 cannot exit otherwise.

## FEATURE — eligible for the model matrix (79)

| column | justification |
|---|---|
| `loan_amnt` | requested amount, stated on the application |
| `term` | chosen product term; v1 scope filters to 36 months (Charter §3.3) |
| `purpose` | borrower-declared purpose; closed 14-value vocabulary |
| `emp_length` | employment length, application field, 11-value vocabulary |
| `home_ownership` | application field, closed vocabulary |
| `annual_inc` | self-reported income (limitation recorded in Charter §8) |
| `application_type` | individual vs joint — application structure, known at submission |
| `zip_code` | masked 3-digit zip; geographic proxy — fairness-slice obligation (R7), not a ban |
| `addr_state` | state; same fairness-slice obligation as zip_code |
| `dti` | debt-to-income from bureau + stated income; measured -1..999, treatment is a P4 decision |
| `delinq_2yrs` | bureau: delinquencies in trailing 24 months |
| `earliest_cr_line` | bureau: first credit line date; used as credit-history-length, always <= issue_d (contract invariant) |
| `fico_range_low` | bureau: FICO band lower bound at application |
| `fico_range_high` | bureau: FICO band upper bound at application |
| `inq_last_6mths` | bureau: hard inquiries, trailing 6 months |
| `mths_since_last_delinq` | bureau; 51% null where null = no delinquency on record (meaningful null) |
| `mths_since_last_record` | bureau; 84% null where null = no public record (meaningful null) |
| `open_acc` | bureau: open credit lines |
| `pub_rec` | bureau: derogatory public records |
| `revol_bal` | bureau: revolving balance |
| `revol_util` | bureau: revolving utilisation; >100% is real (over-limit) |
| `total_acc` | bureau: total credit lines ever |
| `collections_12_mths_ex_med` | bureau: collections excl. medical, trailing 12 months |
| `mths_since_last_major_derog` | bureau; 74% null = no major derogatory (meaningful null) |
| `acc_now_delinq` | bureau: accounts currently delinquent (borrower's other accounts, at application) |
| `tot_coll_amt` | bureau: total collection amounts ever owed |
| `tot_cur_bal` | bureau: total current balance, all accounts |
| `acc_open_past_24mths` | bureau: accounts opened, trailing 24 months |
| `avg_cur_bal` | bureau: average current balance |
| `bc_open_to_buy` | bureau: bankcard open-to-buy |
| `bc_util` | bureau: bankcard utilisation |
| `chargeoff_within_12_mths` | bureau: borrower's own charge-offs in trailing 12 months — their history, not this loan's outcome |
| `delinq_amnt` | bureau: amount currently delinquent |
| `mo_sin_old_il_acct` | bureau: months since oldest installment account |
| `mo_sin_old_rev_tl_op` | bureau: months since oldest revolving line |
| `mo_sin_rcnt_rev_tl_op` | bureau: months since newest revolving line |
| `mo_sin_rcnt_tl` | bureau: months since newest account |
| `mort_acc` | bureau: mortgage accounts |
| `mths_since_recent_bc` | bureau: months since newest bankcard |
| `mths_since_recent_bc_dlq` | bureau; high null = no bankcard delinquency (meaningful null) |
| `mths_since_recent_inq` | bureau: months since most recent inquiry |
| `mths_since_recent_revol_delinq` | bureau; high null = no revolving delinquency (meaningful null) |
| `num_accts_ever_120_pd` | bureau: accounts ever 120+ days past due |
| `num_actv_bc_tl` | bureau: active bankcard lines |
| `num_actv_rev_tl` | bureau: active revolving lines |
| `num_bc_sats` | bureau: satisfactory bankcard accounts |
| `num_bc_tl` | bureau: bankcard lines |
| `num_il_tl` | bureau: installment lines |
| `num_op_rev_tl` | bureau: open revolving lines |
| `num_rev_accts` | bureau: revolving accounts |
| `num_rev_tl_bal_gt_0` | bureau: revolving lines with balance |
| `num_sats` | bureau: satisfactory accounts |
| `num_tl_120dpd_2m` | bureau: lines 120+ dpd in last 2 months |
| `num_tl_30dpd` | bureau: lines 30+ dpd |
| `num_tl_90g_dpd_24m` | bureau: lines 90+ dpd, trailing 24 months |
| `num_tl_op_past_12m` | bureau: lines opened, trailing 12 months |
| `pct_tl_nvr_dlq` | bureau: percent of lines never delinquent |
| `percent_bc_gt_75` | bureau: percent of bankcards >75% utilised |
| `pub_rec_bankruptcies` | bureau: bankruptcy public records |
| `tax_liens` | bureau: tax liens |
| `tot_hi_cred_lim` | bureau: total high credit limit |
| `total_bal_ex_mort` | bureau: total balance excluding mortgage |
| `total_bc_limit` | bureau: bankcard limit |
| `total_il_high_credit_limit` | bureau: installment high credit limit |
| `total_rev_hi_lim` | bureau: revolving high limit |
| `open_acc_6m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_act_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_il_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_il_24m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `mths_since_rcnt_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `total_bal_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `il_util` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_rv_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_rv_24m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `max_bal_bc` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `all_util` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `inq_fi` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `total_cu_tl` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `inq_last_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |

## BANNED_POST — populated after origination (leakage) (38)

| column | justification |
|---|---|
| `pymnt_plan` | on-a-payment-plan flag; servicing state |
| `out_prncp` | outstanding principal now; repayment state |
| `out_prncp_inv` | outstanding principal, investor share |
| `total_pymnt` | total paid to date |
| `total_pymnt_inv` | total paid, investor share |
| `total_rec_prncp` | principal received to date |
| `total_rec_int` | interest received to date |
| `total_rec_late_fee` | late fees received — near-direct outcome encoding |
| `recoveries` | post-charge-off recoveries — nonzero implies the target |
| `collection_recovery_fee` | collection fees — implies charge-off |
| `last_pymnt_d` | last payment date; banned as feature (note: legitimate later for label-timing arithmetic, which is not feature use) |
| `last_pymnt_amnt` | last payment amount |
| `next_pymnt_d` | next scheduled payment; only exists for live loans |
| `last_credit_pull_d` | date LC last re-pulled credit, during servicing |
| `last_fico_range_high` | FICO at last re-pull — the classic subtle leak: post-origination score |
| `last_fico_range_low` | FICO at last re-pull |
| `hardship_flag` | entered hardship program during life of loan |
| `hardship_type` | hardship program detail |
| `hardship_reason` | hardship program detail |
| `hardship_status` | hardship program detail |
| `deferral_term` | hardship program detail |
| `hardship_amount` | hardship program detail |
| `hardship_start_date` | hardship program detail |
| `hardship_end_date` | hardship program detail |
| `payment_plan_start_date` | hardship program detail |
| `hardship_length` | hardship program detail |
| `hardship_dpd` | hardship: days past due |
| `hardship_loan_status` | loan status at hardship start — literally a later status |
| `orig_projected_additional_accrued_interest` | hardship accounting detail |
| `hardship_payoff_balance_amount` | hardship accounting detail |
| `hardship_last_payment_amount` | hardship accounting detail |
| `debt_settlement_flag` | borrower settled with a third party — outcome-adjacent |
| `debt_settlement_flag_date` | settlement detail |
| `settlement_status` | settlement detail |
| `settlement_date` | settlement detail |
| `settlement_amount` | settlement detail |
| `settlement_percentage` | settlement detail |
| `settlement_term` | settlement detail |

## BANNED_UNDERWRITING — LC's own credit-assessment outputs (Charter §1) (4)

| column | justification |
|---|---|
| `int_rate` | LC's priced rate — their model's output, not borrower information |
| `grade` | LC risk grade — their model's output |
| `sub_grade` | LC risk sub-grade — their model's output |
| `installment` | monthly payment = f(amount, term, int_rate); smuggles the banned rate back in |

## TARGET — outcome source (1)

| column | justification |
|---|---|
| `loan_status` | outcome source; labels.py derives the binary target from it |

## METADATA — identifiers / process / split keys (5)

| column | justification |
|---|---|
| `id` | loan identifier; join key for splits and prediction store, never a feature |
| `member_id` | 100% null in this distribution; dead column |
| `url` | listing URL; unique per row, no information beyond id |
| `policy_code` | constant 1 across all rows; zero variance |
| `issue_d` | origination month; the vintage-split key — using calendar time as a feature would not transfer to serving |

## UNDECIDED — must be zero at P2 exit (24)

| column | justification |
|---|---|
| `title` | free-text near-duplicate of purpose (63k uniques); app-time but text — keep only if trivially normalisable, else backlog with desc |
| `desc` | free-text description, 94% null after 2014 (LC removed the field); NLP is backlogged — likely METADATA |
| `emp_title` | free-text job title, 513k uniques; app-time but unusable without NLP — backlog candidate |
| `funded_amnt` | amount actually funded — finalised during listing, after application; lean BAN as process outcome |
| `funded_amnt_inv` | investor-funded portion; same timing question as funded_amnt, plus investor behaviour |
| `initial_list_status` | whole-vs-fractional listing type — LC platform decision at listing, not borrower info; lean BAN |
| `disbursement_method` | Cash vs DirectPay — plausibly chosen at application, verify timing; lean FEATURE |
| `verification_status` | income verification may complete during listing, after submission; widely used in literature — verify timing basis |
| `annual_inc_joint` | joint applications only (95% null); app-time if kept — decide joint-app feature policy as a group |
| `dti_joint` | joint applications only; same group decision |
| `verification_status_joint` | joint applications only; inherits the verification timing question too |
| `revol_bal_joint` | joint applications only; same group decision |
| `sec_app_fico_range_low` | secondary applicant bureau (95% null); same group decision |
| `sec_app_fico_range_high` | secondary applicant bureau; same group decision |
| `sec_app_earliest_cr_line` | secondary applicant bureau; same group decision |
| `sec_app_inq_last_6mths` | secondary applicant bureau; same group decision |
| `sec_app_mort_acc` | secondary applicant bureau; same group decision |
| `sec_app_open_acc` | secondary applicant bureau; same group decision |
| `sec_app_revol_util` | secondary applicant bureau; same group decision |
| `sec_app_open_act_il` | secondary applicant bureau; same group decision |
| `sec_app_num_rev_accts` | secondary applicant bureau; same group decision |
| `sec_app_chargeoff_within_12_mths` | secondary applicant bureau; same group decision |
| `sec_app_collections_12_mths_ex_med` | secondary applicant bureau; same group decision |
| `sec_app_mths_since_last_major_derog` | secondary applicant bureau; same group decision |

