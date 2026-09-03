"""Leakage ledger: classification of every raw column, as code.

This is the P2 audit in importable form. The rendered document
(docs/LEAKAGE_LEDGER.md) is generated from this module by
scripts/render_ledger.py — the dict below is the authority, and the P4
feature pipeline derives its allowlist from it (`feature_columns()`), so a
column cannot be classified one way here and used another way there.

Categories:
- FEATURE ................ knowable at application time; eligible for the model matrix
- BANNED_POST ............ populated after origination; using it is leakage
- BANNED_UNDERWRITING .... known at application but an output of LendingClub's own
                           credit assessment (Charter §1 excludes these by decision)
- TARGET ................. the outcome source; never a feature
- METADATA ............... identifiers / process fields / split keys; never a feature
- UNDECIDED .............. genuinely ambiguous; must be resolved (zero allowed at P2 exit)

Every entry carries a one-line justification. Percentages cited are measured
(docs/SCHEMA.md). First pass (ticket #18): UNDECIDED is allowed and enumerated.
Second pass (ticket #21) must bring UNDECIDED to zero.
"""

from __future__ import annotations

FEATURE = "FEATURE"
BANNED_POST = "BANNED_POST"
BANNED_UNDERWRITING = "BANNED_UNDERWRITING"
TARGET = "TARGET"
METADATA = "METADATA"
UNDECIDED = "UNDECIDED"

CATEGORIES = (FEATURE, BANNED_POST, BANNED_UNDERWRITING, TARGET, METADATA, UNDECIDED)

# Availability caveat shared by the 2015+ bureau block (columns 64-78): these fields
# only start being populated around Dec 2015, so they are ~38-48% null overall and
# mostly null inside the 2013-2015 training window. Application-time legitimate, but
# P4 must handle regime-dependent availability (and drift monitoring must expect it).
_B2015 = "bureau field populated only from ~Dec-2015 (38-48% null); app-time legitimate, availability caveat for the 2013-15 train window"

LEDGER: dict[str, tuple[str, str]] = {
    # --- identifiers / process metadata ---
    "id": (METADATA, "loan identifier; join key for splits and prediction store, never a feature"),
    "member_id": (METADATA, "100% null in this distribution; dead column"),
    "url": (METADATA, "listing URL; unique per row, no information beyond id"),
    "policy_code": (METADATA, "constant 1 across all rows; zero variance"),
    "issue_d": (METADATA, "origination month; the vintage-split key — using calendar time as a feature would not transfer to serving"),
    # --- target ---
    "loan_status": (TARGET, "outcome source; labels.py derives the binary target from it"),
    # --- loan application (borrower-stated) ---
    "loan_amnt": (FEATURE, "requested amount, stated on the application"),
    "term": (FEATURE, "chosen product term; v1 scope filters to 36 months (Charter §3.3)"),
    "purpose": (FEATURE, "borrower-declared purpose; closed 14-value vocabulary"),
    "title": (UNDECIDED, "free-text near-duplicate of purpose (63k uniques); app-time but text — keep only if trivially normalisable, else backlog with desc"),
    "desc": (UNDECIDED, "free-text description, 94% null after 2014 (LC removed the field); NLP is backlogged — likely METADATA"),
    "emp_title": (UNDECIDED, "free-text job title, 513k uniques; app-time but unusable without NLP — backlog candidate"),
    "emp_length": (FEATURE, "employment length, application field, 11-value vocabulary"),
    "home_ownership": (FEATURE, "application field, closed vocabulary"),
    "annual_inc": (FEATURE, "self-reported income (limitation recorded in Charter §8)"),
    "application_type": (FEATURE, "individual vs joint — application structure, known at submission"),
    "zip_code": (FEATURE, "masked 3-digit zip; geographic proxy — fairness-slice obligation (R7), not a ban"),
    "addr_state": (FEATURE, "state; same fairness-slice obligation as zip_code"),
    # --- underwriting outputs (known at application, banned by Charter §1 decision) ---
    "int_rate": (BANNED_UNDERWRITING, "LC's priced rate — their model's output, not borrower information"),
    "grade": (BANNED_UNDERWRITING, "LC risk grade — their model's output"),
    "sub_grade": (BANNED_UNDERWRITING, "LC risk sub-grade — their model's output"),
    "installment": (BANNED_UNDERWRITING, "monthly payment = f(amount, term, int_rate); smuggles the banned rate back in"),
    # --- LC listing/funding process fields ---
    "funded_amnt": (UNDECIDED, "amount actually funded — finalised during listing, after application; lean BAN as process outcome"),
    "funded_amnt_inv": (UNDECIDED, "investor-funded portion; same timing question as funded_amnt, plus investor behaviour"),
    "initial_list_status": (UNDECIDED, "whole-vs-fractional listing type — LC platform decision at listing, not borrower info; lean BAN"),
    "disbursement_method": (UNDECIDED, "Cash vs DirectPay — plausibly chosen at application, verify timing; lean FEATURE"),
    "verification_status": (UNDECIDED, "income verification may complete during listing, after submission; widely used in literature — verify timing basis"),
    # --- bureau snapshot at application (core block) ---
    "dti": (FEATURE, "debt-to-income from bureau + stated income; measured -1..999, treatment is a P4 decision"),
    "delinq_2yrs": (FEATURE, "bureau: delinquencies in trailing 24 months"),
    "earliest_cr_line": (FEATURE, "bureau: first credit line date; used as credit-history-length, always <= issue_d (contract invariant)"),
    "fico_range_low": (FEATURE, "bureau: FICO band lower bound at application"),
    "fico_range_high": (FEATURE, "bureau: FICO band upper bound at application"),
    "inq_last_6mths": (FEATURE, "bureau: hard inquiries, trailing 6 months"),
    "mths_since_last_delinq": (FEATURE, "bureau; 51% null where null = no delinquency on record (meaningful null)"),
    "mths_since_last_record": (FEATURE, "bureau; 84% null where null = no public record (meaningful null)"),
    "open_acc": (FEATURE, "bureau: open credit lines"),
    "pub_rec": (FEATURE, "bureau: derogatory public records"),
    "revol_bal": (FEATURE, "bureau: revolving balance"),
    "revol_util": (FEATURE, "bureau: revolving utilisation; >100% is real (over-limit)"),
    "total_acc": (FEATURE, "bureau: total credit lines ever"),
    "collections_12_mths_ex_med": (FEATURE, "bureau: collections excl. medical, trailing 12 months"),
    "mths_since_last_major_derog": (FEATURE, "bureau; 74% null = no major derogatory (meaningful null)"),
    "acc_now_delinq": (FEATURE, "bureau: accounts currently delinquent (borrower's other accounts, at application)"),
    "tot_coll_amt": (FEATURE, "bureau: total collection amounts ever owed"),
    "tot_cur_bal": (FEATURE, "bureau: total current balance, all accounts"),
    "acc_open_past_24mths": (FEATURE, "bureau: accounts opened, trailing 24 months"),
    "avg_cur_bal": (FEATURE, "bureau: average current balance"),
    "bc_open_to_buy": (FEATURE, "bureau: bankcard open-to-buy"),
    "bc_util": (FEATURE, "bureau: bankcard utilisation"),
    "chargeoff_within_12_mths": (FEATURE, "bureau: borrower's own charge-offs in trailing 12 months — their history, not this loan's outcome"),
    "delinq_amnt": (FEATURE, "bureau: amount currently delinquent"),
    "mo_sin_old_il_acct": (FEATURE, "bureau: months since oldest installment account"),
    "mo_sin_old_rev_tl_op": (FEATURE, "bureau: months since oldest revolving line"),
    "mo_sin_rcnt_rev_tl_op": (FEATURE, "bureau: months since newest revolving line"),
    "mo_sin_rcnt_tl": (FEATURE, "bureau: months since newest account"),
    "mort_acc": (FEATURE, "bureau: mortgage accounts"),
    "mths_since_recent_bc": (FEATURE, "bureau: months since newest bankcard"),
    "mths_since_recent_bc_dlq": (FEATURE, "bureau; high null = no bankcard delinquency (meaningful null)"),
    "mths_since_recent_inq": (FEATURE, "bureau: months since most recent inquiry"),
    "mths_since_recent_revol_delinq": (FEATURE, "bureau; high null = no revolving delinquency (meaningful null)"),
    "num_accts_ever_120_pd": (FEATURE, "bureau: accounts ever 120+ days past due"),
    "num_actv_bc_tl": (FEATURE, "bureau: active bankcard lines"),
    "num_actv_rev_tl": (FEATURE, "bureau: active revolving lines"),
    "num_bc_sats": (FEATURE, "bureau: satisfactory bankcard accounts"),
    "num_bc_tl": (FEATURE, "bureau: bankcard lines"),
    "num_il_tl": (FEATURE, "bureau: installment lines"),
    "num_op_rev_tl": (FEATURE, "bureau: open revolving lines"),
    "num_rev_accts": (FEATURE, "bureau: revolving accounts"),
    "num_rev_tl_bal_gt_0": (FEATURE, "bureau: revolving lines with balance"),
    "num_sats": (FEATURE, "bureau: satisfactory accounts"),
    "num_tl_120dpd_2m": (FEATURE, "bureau: lines 120+ dpd in last 2 months"),
    "num_tl_30dpd": (FEATURE, "bureau: lines 30+ dpd"),
    "num_tl_90g_dpd_24m": (FEATURE, "bureau: lines 90+ dpd, trailing 24 months"),
    "num_tl_op_past_12m": (FEATURE, "bureau: lines opened, trailing 12 months"),
    "pct_tl_nvr_dlq": (FEATURE, "bureau: percent of lines never delinquent"),
    "percent_bc_gt_75": (FEATURE, "bureau: percent of bankcards >75% utilised"),
    "pub_rec_bankruptcies": (FEATURE, "bureau: bankruptcy public records"),
    "tax_liens": (FEATURE, "bureau: tax liens"),
    "tot_hi_cred_lim": (FEATURE, "bureau: total high credit limit"),
    "total_bal_ex_mort": (FEATURE, "bureau: total balance excluding mortgage"),
    "total_bc_limit": (FEATURE, "bureau: bankcard limit"),
    "total_il_high_credit_limit": (FEATURE, "bureau: installment high credit limit"),
    "total_rev_hi_lim": (FEATURE, "bureau: revolving high limit"),
    # --- 2015+ bureau block (availability caveat) ---
    "open_acc_6m": (FEATURE, _B2015),
    "open_act_il": (FEATURE, _B2015),
    "open_il_12m": (FEATURE, _B2015),
    "open_il_24m": (FEATURE, _B2015),
    "mths_since_rcnt_il": (FEATURE, _B2015),
    "total_bal_il": (FEATURE, _B2015),
    "il_util": (FEATURE, _B2015),
    "open_rv_12m": (FEATURE, _B2015),
    "open_rv_24m": (FEATURE, _B2015),
    "max_bal_bc": (FEATURE, _B2015),
    "all_util": (FEATURE, _B2015),
    "inq_fi": (FEATURE, _B2015),
    "total_cu_tl": (FEATURE, _B2015),
    "inq_last_12m": (FEATURE, _B2015),
    # --- joint / secondary applicant (structural nulls; group decision in pass 2) ---
    "annual_inc_joint": (UNDECIDED, "joint applications only (95% null); app-time if kept — decide joint-app feature policy as a group"),
    "dti_joint": (UNDECIDED, "joint applications only; same group decision"),
    "verification_status_joint": (UNDECIDED, "joint applications only; inherits the verification timing question too"),
    "revol_bal_joint": (UNDECIDED, "joint applications only; same group decision"),
    "sec_app_fico_range_low": (UNDECIDED, "secondary applicant bureau (95% null); same group decision"),
    "sec_app_fico_range_high": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_earliest_cr_line": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_inq_last_6mths": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_mort_acc": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_open_acc": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_revol_util": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_open_act_il": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_num_rev_accts": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_chargeoff_within_12_mths": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_collections_12_mths_ex_med": (UNDECIDED, "secondary applicant bureau; same group decision"),
    "sec_app_mths_since_last_major_derog": (UNDECIDED, "secondary applicant bureau; same group decision"),
    # --- post-origination: loan servicing / repayment (unambiguous leakage) ---
    "pymnt_plan": (BANNED_POST, "on-a-payment-plan flag; servicing state"),
    "out_prncp": (BANNED_POST, "outstanding principal now; repayment state"),
    "out_prncp_inv": (BANNED_POST, "outstanding principal, investor share"),
    "total_pymnt": (BANNED_POST, "total paid to date"),
    "total_pymnt_inv": (BANNED_POST, "total paid, investor share"),
    "total_rec_prncp": (BANNED_POST, "principal received to date"),
    "total_rec_int": (BANNED_POST, "interest received to date"),
    "total_rec_late_fee": (BANNED_POST, "late fees received — near-direct outcome encoding"),
    "recoveries": (BANNED_POST, "post-charge-off recoveries — nonzero implies the target"),
    "collection_recovery_fee": (BANNED_POST, "collection fees — implies charge-off"),
    "last_pymnt_d": (BANNED_POST, "last payment date; banned as feature (note: legitimate later for label-timing arithmetic, which is not feature use)"),
    "last_pymnt_amnt": (BANNED_POST, "last payment amount"),
    "next_pymnt_d": (BANNED_POST, "next scheduled payment; only exists for live loans"),
    "last_credit_pull_d": (BANNED_POST, "date LC last re-pulled credit, during servicing"),
    "last_fico_range_high": (BANNED_POST, "FICO at last re-pull — the classic subtle leak: post-origination score"),
    "last_fico_range_low": (BANNED_POST, "FICO at last re-pull"),
    # --- post-origination: hardship program ---
    "hardship_flag": (BANNED_POST, "entered hardship program during life of loan"),
    "hardship_type": (BANNED_POST, "hardship program detail"),
    "hardship_reason": (BANNED_POST, "hardship program detail"),
    "hardship_status": (BANNED_POST, "hardship program detail"),
    "deferral_term": (BANNED_POST, "hardship program detail"),
    "hardship_amount": (BANNED_POST, "hardship program detail"),
    "hardship_start_date": (BANNED_POST, "hardship program detail"),
    "hardship_end_date": (BANNED_POST, "hardship program detail"),
    "payment_plan_start_date": (BANNED_POST, "hardship program detail"),
    "hardship_length": (BANNED_POST, "hardship program detail"),
    "hardship_dpd": (BANNED_POST, "hardship: days past due"),
    "hardship_loan_status": (BANNED_POST, "loan status at hardship start — literally a later status"),
    "orig_projected_additional_accrued_interest": (BANNED_POST, "hardship accounting detail"),
    "hardship_payoff_balance_amount": (BANNED_POST, "hardship accounting detail"),
    "hardship_last_payment_amount": (BANNED_POST, "hardship accounting detail"),
    # --- post-origination: debt settlement ---
    "debt_settlement_flag": (BANNED_POST, "borrower settled with a third party — outcome-adjacent"),
    "debt_settlement_flag_date": (BANNED_POST, "settlement detail"),
    "settlement_status": (BANNED_POST, "settlement detail"),
    "settlement_date": (BANNED_POST, "settlement detail"),
    "settlement_amount": (BANNED_POST, "settlement detail"),
    "settlement_percentage": (BANNED_POST, "settlement detail"),
    "settlement_term": (BANNED_POST, "settlement detail"),
}


def columns_in(category: str) -> list[str]:
    return [c for c, (cat, _) in LEDGER.items() if cat == category]


def feature_columns() -> list[str]:
    """The only columns eligible for the model matrix. P4 imports this."""
    return columns_in(FEATURE)


def undecided_columns() -> list[str]:
    return columns_in(UNDECIDED)
