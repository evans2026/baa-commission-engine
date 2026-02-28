# **BAA Commission Engine – Required Fixes & Enhancements (Authoritative Specification)**

### ***Implementation Directive for Agent***

This document defines the mandatory changes required to upgrade the BAA Commission Engine into a fully robust, audit‑ready, multi‑scheme profit‑commission engine capable of handling the full range of incentive‑based structures found in 2026 Binding Authority Agreements. All items below are required and must include updated tests, schema migrations, and full backward compatibility.

## **1\. Schema Corrections (Critical)**

### **Fix commission\_ledger schema mismatch**

The current schema is missing fields that the engine writes. Add:

* `carrier_split_effective_from` (DATE)  
* `carrier_split_pct` (NUMERIC)

Both must be `NOT NULL`.

Backfill existing rows with safe defaults.

## **2\. Correct Carrier Split Vintage Logic (Critical)**

### **Problem**

`get_carrier_splits` currently returns *all* rows with `effective_from <= as_of_date`, which breaks when multiple vintages exist.

### **Required Implementation**

Rewrite `get_carrier_splits` to:

* Select **latest row per carrier** where `effective_from <= as_of_date`.  
* Use window functions or grouping to enforce one row per carrier.  
* Validate that the sum of `participation_pct` ≈ 1.0 (±0.0001).  
* Raise a clear error if invalid.

### **Tests Required**

* Multiple vintages per carrier.  
* Carriers entering/exiting mid‑term.  
* Vintage selection at different as‑of dates.

## **3\. Implement Profit‑Commission Scheme Engine (Major)**

The engine must support multiple types of incentive‑based profit commission, not just a single sliding scale.

### **New Table: profit\_commission\_schemes**

Fields:

* `scheme_id` (PK)  
* `scheme_type` (enum: `sliding_scale`, `corridor`, `fixed_plus_variable`, `capped_scale`, `carrier_specific_scale`)  
* `parameters_json` (JSONB)  
* `effective_from`  
* `effective_to`  
* `system_timestamp`

### **New Table: baa\_contract\_versions**

Fields:

* `baa_id`  
* `program_id`  
* `underwriting_year`  
* `scheme_id`  
* `effective_from`  
* `system_timestamp`

### **Engine Requirements**

* `run_trueup` must:  
  * Determine the correct scheme for the UY and as‑of date.  
  * Dispatch to the correct commission calculator based on `scheme_type`.  
  * Use parameters from `parameters_json`.

### **Scheme Types to Implement**

1. Sliding scale (existing logic)  
2. Corridor commission (0% between LR bands)  
3. Fixed \+ variable (e.g., 10% fixed \+ variable override)  
4. Capped scale (max commission %)  
5. Carrier‑specific scales

### **Tests Required**

* Scheme selection by date.  
* Scheme version changes mid‑runoff.  
* Full test suite for each scheme type.

## **4\. Add Multi‑BAA / Multi‑Program Support (Major)**

### **Required Changes**

Add `baa_id` and `program_id` to:

* `transactions`  
* `carrier_splits`  
* `ibnr_snapshots`  
* `commission_ledger`

### **Query Requirements**

All queries must filter by:

Code  
WHERE baa\_id \= ?  
  AND program\_id \= ?  
  AND underwriting\_year \= ?

### **Tests Required**

* Two BAAs with same UY but different carriers.  
* Two programs with different profit‑commission schemes.

## **5\. Add Multi‑Currency & FX Handling (Major)**

### **Required Changes**

Add `currency` to:

* `transactions`  
* `ibnr_snapshots`  
* `commission_ledger`

### **New Table: fx\_rates**

Fields:

* `currency`  
* `date`  
* `rate_to_base`  
* `system_timestamp`

### **Engine Requirements**

* Convert all amounts to a canonical currency (USD) using `as_of_date` FX.  
* Store both original and converted amounts in ledger.

### **Tests Required**

* Mixed‑currency premium and claims.  
* FX changes across as‑of dates.

## **6\. Add Negative Commission & Clawback Rules (Major)**

### **Required Parameters**

Add to scheme parameters:

* `allow_negative_commission`  
* `commission_floor_pct`  
* `commission_cap_pct`  
* `aggregate_cap_pct`  
* `multi_year_cap`

### **Engine Requirements**

* Allow negative deltas if permitted.  
* Enforce floor and cap rules.  
* Track aggregate caps across years if enabled.

### **Tests Required**

* Negative commission allowed.  
* Negative commission disallowed.  
* Cap enforcement.  
* Multi‑year cap enforcement.

## **7\. Add LPT / Commutation Handling (Moderate)**

### **New Table: lpt\_events**

Fields:

* `carrier_id`  
* `baa_id`  
* `program_id`  
* `underwriting_year`  
* `effective_date`  
* `freeze_commission`

### **Engine Requirements**

* Stop calculating commission for carriers after LPT date.  
* Write ledger entries indicating freeze.

### **Tests Required**

* LPT mid‑runoff.  
* LPT before first true‑up.

## **8\. Add As‑Of System State Replay (Moderate)**

### **Required Changes**

Add optional parameter:

Code  
system\_as\_of\_timestamp

All queries must filter:

Code  
system\_timestamp \<= system\_as\_of\_timestamp

### **Tests Required**

* Reproducing historical true‑ups.  
* Differences between system states.

## **9\. Improve IBNR Logic (Moderate)**

### **Required Changes**

* Enforce `as_of_date <= eval_date`.  
* Warn if violated.  
* Add support for per‑carrier IBNR.  
* Fallback to cohort IBNR if carrier IBNR missing.

### **Tests Required**

* Per‑carrier IBNR.  
* Fallback behavior.

## **10\. Improve Earned Premium Logic (Minor)**

### **Required Changes**

Add support for:

* Earned premium override per UY.  
* Pro‑rata earned premium based on inception/expiration dates.

### **Tests Required**

* Partial‑year earned premium.  
* Override behavior.

## **11\. Improve Development Month Handling (Minor)**

### **Required Changes**

* Use `development_month` from IBNR snapshot.  
* Remove any implicit calendar‑based inference.

### **Tests Required**

* Non‑linear dev month sequences.  
* Rebased dev months.

## **12\. Code Quality Requirements**

### **Required Changes**

* Add docstrings to all functions.  
* Add full type hints.  
* Remove dead code.  
* Ensure 100% test coverage.  
* Ensure all warnings are resolved or explicitly suppressed.

## **Final Deliverables**

The final implementation must include:

* Updated schema migrations.  
* Updated engine logic.  
* New profit‑commission scheme engine.  
* Updated tests (minimum \+30 new tests).  
* Updated documentation in README.  
* Zero failing tests.

