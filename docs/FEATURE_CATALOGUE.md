# Feature Catalogue

GENERATED from `src/credit_default/features/catalogue.py` — edit code, rerun
`scripts/render_feature_catalogue.py`. A test asserts this file matches the code.

Status: STARTED (#29, skeleton transforms). Finalised at P4 exit (#32) once the
#30 transform decisions (scaling, zip_code encoding, dti treatment) land.

Matrix composition: 71 numeric + 1 engineered + one-hot expansions of 7 categoricals. Every feature's application-time justification is inherited verbatim from the leakage ledger; a column without a FEATURE verdict there cannot appear here.

## Engineered features

| Feature | Definition | Source columns | Transform | Application-time justification |
|---|---|---|---|---|
| `credit_history_months` | Age of the credit file at application, in months | `issue_d`, `earliest_cr_line` | (issue year-month − earliest year-month); then median impute | Both dates are on the application; the difference is known the moment it is submitted. `issue_d` itself is never a feature (METADATA: calendar time would not transfer to serving). |

## Categorical features (7)

Transform, all rows: impute constant "missing" -> one-hot (categories learned on the training split; unknown values at serving time encode as all-zeros, never an error).

| Feature | Values | Application-time justification (ledger) |
|---|---|---|
| `addr_state` | 51 categories | state; same fairness-slice obligation as zip_code |
| `application_type` | 2 categories | individual vs joint — application structure, known at submission |
| `disbursement_method` | 2 categories | borrower's choice at application (Cash vs DirectPay-to-creditors); known at submission |
| `emp_length` | 11 categories | employment length, application field, 11-value vocabulary |
| `home_ownership` | 6 categories | application field, closed vocabulary |
| `purpose` | 14 categories | borrower-declared purpose; closed 14-value vocabulary |
| `verification_status` | 3 categories | verification completes during listing, before origination — the charter's decision point; serving contract must capture status as-of decision time |

## Numeric features (71)

Transform, all rows: median impute (median learned on the training split only). Bounds enforced upstream by the
data contract (`docs/DATA_CONTRACT.md`); meaningful nulls are imputed, and
whether null-indicator columns should be added is a #30 decision.

| Feature | Application-time justification (ledger) |
|---|---|
| `acc_now_delinq` | bureau: accounts currently delinquent (borrower's other accounts, at application) |
| `acc_open_past_24mths` | bureau: accounts opened, trailing 24 months |
| `all_util` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `annual_inc` | self-reported income (limitation recorded in Charter §8) |
| `avg_cur_bal` | bureau: average current balance |
| `bc_open_to_buy` | bureau: bankcard open-to-buy |
| `bc_util` | bureau: bankcard utilisation |
| `chargeoff_within_12_mths` | bureau: borrower's own charge-offs in trailing 12 months — their history, not this loan's outcome |
| `collections_12_mths_ex_med` | bureau: collections excl. medical, trailing 12 months |
| `delinq_2yrs` | bureau: delinquencies in trailing 24 months |
| `delinq_amnt` | bureau: amount currently delinquent |
| `dti` | debt-to-income from bureau + stated income; measured -1..999, treatment is a P4 decision |
| `fico_range_high` | bureau: FICO band upper bound at application |
| `fico_range_low` | bureau: FICO band lower bound at application |
| `il_util` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `inq_fi` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `inq_last_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `inq_last_6mths` | bureau: hard inquiries, trailing 6 months |
| `loan_amnt` | requested amount, stated on the application |
| `max_bal_bc` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `mo_sin_old_il_acct` | bureau: months since oldest installment account |
| `mo_sin_old_rev_tl_op` | bureau: months since oldest revolving line |
| `mo_sin_rcnt_rev_tl_op` | bureau: months since newest revolving line |
| `mo_sin_rcnt_tl` | bureau: months since newest account |
| `mort_acc` | bureau: mortgage accounts |
| `mths_since_last_delinq` | bureau; 51% null where null = no delinquency on record (meaningful null) |
| `mths_since_last_major_derog` | bureau; 74% null = no major derogatory (meaningful null) |
| `mths_since_last_record` | bureau; 84% null where null = no public record (meaningful null) |
| `mths_since_rcnt_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
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
| `open_acc` | bureau: open credit lines |
| `open_acc_6m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_act_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_il_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_il_24m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_rv_12m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `open_rv_24m` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `pct_tl_nvr_dlq` | bureau: percent of lines never delinquent |
| `percent_bc_gt_75` | bureau: percent of bankcards >75% utilised |
| `pub_rec` | bureau: derogatory public records |
| `pub_rec_bankruptcies` | bureau: bankruptcy public records |
| `revol_bal` | bureau: revolving balance |
| `revol_util` | bureau: revolving utilisation; >100% is real (over-limit) |
| `tax_liens` | bureau: tax liens |
| `tot_coll_amt` | bureau: total collection amounts ever owed |
| `tot_cur_bal` | bureau: total current balance, all accounts |
| `tot_hi_cred_lim` | bureau: total high credit limit |
| `total_acc` | bureau: total credit lines ever |
| `total_bal_ex_mort` | bureau: total balance excluding mortgage |
| `total_bal_il` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `total_bc_limit` | bureau: bankcard limit |
| `total_cu_tl` | bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window |
| `total_il_high_credit_limit` | bureau: installment high credit limit |
| `total_rev_hi_lim` | bureau: revolving high limit |

## FEATURE columns deliberately not in the v1 matrix

Ledger verdict FEATURE (legitimate), excluded by pipeline scope decision:

| Column | Reason |
|---|---|
| `term` | constant ' 36 months' in v1 scope (Charter §3.3) — zero variance by construction |
| `zip_code` | 956-value masked geography; needs frequency/target encoding designed in #30 — addr_state carries geography until then |
