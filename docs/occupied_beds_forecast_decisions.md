# Occupied-Bed Forecast Decisions

## Status
Historical monthly calibration and an LOS-driven admissions/discharges turnover master daily dataset (Option B) are complete for 2017–2024, with total occupied beds now the sum of 9 sections rather than an independently reconciled series. Forecasting for 2025–2026 remains pending.

## Confirmed decisions

- **Modeling target:** daily occupied-bed counts for a representative individual hospital.
- **Source series:** `Average_number_of_occupied_beds_per_day` from `Health_data_generation_notebook.ipynb`.
- **Observed data granularity:** monthly aggregate observations, currently covering January 2017 through December 2024.
- **Seasonality:** the forecast must account for seasonal patterns.
- **Realism requirement:** generated daily values should vary from day to day rather than repeating the monthly average.
- **Population scope:** estimate historical occupancy for VCU Medical Center rather than an equal-share representative hospital.
- **Equal-share comparison:** retain statewide occupancy divided by 317 only as a comparison that illustrates why hospital size must be considered.
- **Historical daily reconstruction:** generate synthetic daily values for every day from January 2017 through December 2024 from the monthly aggregate series.
- **Forecast target period:** generate forecasts for every day in 2025 and 2026, using the reconstructed 2017–2024 daily series as the modeling history.
- **COVID signal:** retain the COVID-19 series as a factor because COVID affects potential bed demand and capacity.
- **Hospital-specific reference data:** use the American Hospital Directory Virginia hospital statistics to compare hospital scale and derive reference census and occupancy measures for Richmond hospitals.
- **Selected hospital:** use VCU Medical Center as the hospital-specific target, with 905 staffed beds and 247,208 annual patient days from the supplied AHD record.
- **VCU baseline:** derive an estimated annual average daily census as `247,208 / 365.25 = 676.82` occupied beds and an estimated annual occupancy rate of 74.79%.
- **Historical calibration:** estimate each VCU monthly census as the corresponding statewide monthly census multiplied by VCU's calibrated 2024 statewide share.
- **Statewide comparison:** Virginia's date-aligned 2024 monthly occupied-bed series averages 12,239.17 beds. VCU's estimated 676.82 occupied beds represent about 5.53% of that statewide census.
- **Equal-share normalization:** do not use statewide occupancy divided by 317 as VCU's baseline. Its 2024 value of 38.61 occupied beds is only a statewide equal-share comparison and does not account for hospital size.
- **Daily generation:** use a seeded AR(1) process around each modeled monthly VCU mean to create autocorrelated daily variation.
- **Daily variability:** use an assumed coefficient of variation of 3% and persistence of 0.85.
- **Daily constraints:** produce non-negative integer counts capped at VCU's 905 staffed beds and reconcile each month to its rounded target patient-days.
- **Metric taxonomy:** treat intensive occupancy as a bed census; treat newborn, delivery, elective/non-elective, COVID-19, influenza, and other viral values as average length-of-stay metrics rather than additive bed categories.
- **Influenza imputation:** replace 13 suppressed `***` values with the median observed length of stay for the same calendar month.
- **COVID alignment:** exclude the 36 pre-outbreak zero placeholders from January 2017 through December 2019; use January 2020 through September 2024 as the observed window and leave October–December 2024 unavailable.
- **VCU intensive estimate:** apply Virginia's monthly intensive-bed share to modeled VCU total occupancy.
- **Aggregate patient flow:** derive VCU average LOS from annual patient days divided by discharges and estimate admissions, discharges, and overnight carryover under steady-state balance.
- **Reproducibility:** the eventual stochastic generation must use an explicit seed, consistent with the project instructions.

## Data limitations already identified

- The source series is monthly and does not provide observed day-to-day variation; daily values from 2017–2024 will therefore be reconstructed rather than observed.
- The current notebook does not establish whether the counts represent Virginia statewide occupancy or a single hospital/unit; the value scale suggests an aggregate series, but this must be confirmed.
- The current notebook does not document a daily variance, forecast horizon, or treatment of unusual periods such as COVID-19.
- Dividing by 317 assumes the hospital count is constant and that statewide occupancy can be allocated evenly to a representative hospital; this is a modeling approximation, not an observed hospital-level series.
- The source provenance and definition of "occupied beds" need to be confirmed before the result is treated as a validated forecast.
- The AHD page reports each hospital's most recent cost report and other sources, so the hospital-level values are not necessarily from the same reporting year as one another or as the 2017–2024 monthly series.
- AHD lists several Richmond-area facilities with zero values; these should not be treated as zero-capacity operating hospitals without confirming what the zero represents.
- Applying a constant 5.53% statewide share assumes VCU followed Virginia's historical trend and seasonality; the resulting 2017–2024 values are modeled estimates, not VCU observations.
- The 3% daily variability and 0.85 persistence are synthetic assumptions because no observed VCU daily census series is available.
- Monthly data supports monthly seasonality but cannot establish a weekday, holiday, or other within-month seasonal pattern. The daily process models correlated variation, not measured daily seasonality.
- Admission-route, diagnosis, and bed-type groups overlap and cannot be summed without double counting.
- Length of stay alone cannot determine occupied beds by category; category-specific admission or discharge volumes are required.
- The intensive minimum series ends at 7 while its paired average is 903 and maximum is 1,528. Intensive minimum and maximum series are excluded until the source is verified.
- December 2024 total and intensive occupancy also decline sharply, suggesting a potentially incomplete or anomalous latest month that should be resolved before forecasting.
- Applying the statewide intensive share to VCU may underestimate intensive use at a tertiary medical center.
- Pre-2020 COVID-19 zeros are structural placeholders, not measured zero-day stays, and must never enter summaries, imputation, or model fitting.
- Length of stay is only observed monthly; daily LOS values are a stochastic reconstruction (AR(1), rescaled to the monthly mean), not measured daily LOS.
- No per-category (ward) bed-pool data exists; the model assumes hospitals flexibly reassign capacity across sections rather than reserving fixed per-ward beds.
- The turnover recurrence trades exact monthly reconciliation for LOS-driven day-to-day dynamics; volatile categories (influenza, max error 24.9 beds; COVID-19, 13.1 beds) drift further from their monthly target than stable categories (newborn, 4.7 beds) because the system needs roughly one LOS-cycle to re-equilibrate after a target shift.
- ICU has no published LOS; its turnover discharges use VCU's overall constant average LOS (5.91 days) as a stand-in, which may not reflect actual ICU stay duration.

## Open decisions

1. **COVID role:** Should COVID be a separate additive demand adjustment, a capacity constraint, or simply a documented contextual variable while ordinary seasonality is estimated from occupancy?
2. **Within-month seasonality:** Should a future version add assumed weekday or holiday effects, or retain only autocorrelated daily variation until supporting data is available?
3. **December 2024:** Is the final month complete, or should it be excluded or imputed before fitting the 2025–2026 forecast?
4. **Category volumes:** Can we obtain monthly admissions or discharges for newborn, delivery, elective, non-elective, COVID-19, influenza, and other viral groups?
5. **ICU length of stay:** No ICU-specific LOS can be derived from this dataset (it is mathematically identical to the hospital-wide average given current assumptions). Keep the hospital-wide LOS stand-in, or supply an external benchmark/source to replace it?
6. **December 2024 data quality:** Is the sharp December 2024 drop a genuine decline, or a preliminary/partial-month reporting artifact in the source table? Needs checking against the original HCUP/AHRQ table for revision footnotes.
7. **Seasonal COVID-19 projection:** The fitted exponential-decay floor (106.08 beds) ignores the recurring winter waves visible in the data (e.g., ~126 beds in Dec 2022, ~125 in Nov 2023) and likely understates a December 2024 seasonal uptick. Add a seasonal adjustment, or accept the flat floor estimate?

## Decision log

| Date | Decision | Rationale | Evidence or owner |
|---|---|---|---|
| 2026-09-30 | Use the occupied-bed average series as the forecast target. | Matches the requested modeling task. | User request |
| 2026-09-30 | Include seasonality. | Matches the requested modeling task. | User request |
| 2026-09-30 | Treat daily variation as generated rather than observed. | The available series is monthly aggregate data. | Notebook inspection |
| 2026-09-30 | Normalize statewide occupancy across 317 hospitals to a synthetic individual hospital. | The source values represent all 317 Virginia hospitals. | User clarification |
| 2026-09-30 | Reconstruct daily occupancy for January 2017 through December 2024, then forecast daily occupancy for 2025 and 2026. | The user needs daily information from the beginning of the available data and both forecast years. | User clarification |
| 2026-09-30 | Retain COVID-19 information in the modeling inputs. | COVID affects potential bed demand and capacity. | User clarification |
| 2026-10-01 | Normalize the monthly occupied-bed array with NumPy by dividing by 317 hospitals. | Produces a separate per-hospital monthly baseline without changing the source series. | Notebook execution |
| 2026-10-01 | Add Richmond hospital reference records from the American Hospital Directory. | The statewide average does not match Richmond hospital scale; hospital-level staffed beds and patient days provide a local comparison. | User-provided AHD data and notebook execution |
| 2026-10-01 | Derive estimated average daily census as patient days divided by 365.25 and occupancy rate as patient days divided by staffed beds times 365.25. | Converts the supplied hospital summary fields into comparable reference measures. | Notebook calculation; reporting period remains approximate |
| 2026-10-01 | Select VCU Medical Center as the target hospital. | The user wants a Richmond-specific hospital rather than an equal-share statewide representative. | User decision |
| 2026-10-01 | Use 676.82 occupied beds and 74.79% occupancy as VCU's annual baseline. | Derived from 247,208 patient days and 905 staffed beds. | AHD data supplied by user |
| 2026-10-01 | Retire the equal-share 317-hospital estimate as the VCU modeling baseline. | VCU is a 905-bed tertiary center; its estimated census is 5.53% of Virginia's date-aligned 2024 statewide census and 17.53 times the equal-share estimate. | Notebook comparison of AHD VCU data with the statewide monthly series |
| 2026-10-01 | Estimate VCU's 2017–2024 monthly history by applying its calibrated 5.53% share to each statewide monthly census. | Preserves the observed statewide historical and seasonal shape while anchoring 2024 to VCU's 676.82-bed reference census. | User-approved direction and notebook validation |
| 2026-10-01 | Correct the earlier 2024 comparison to use the actual date-aligned final 12 values. | The earlier manual calculation selected the wrong 12-value slice; notebook validation gives a 12,239.17 statewide mean. | Notebook validation |
| 2026-10-01 | Generate daily census with a seeded AR(1) process using 3% variability and 0.85 persistence. | Occupancy is correlated from one day to the next; no observed VCU daily series is available to estimate these parameters. | Documented modeling assumption |
| 2026-10-01 | Constrain daily census to integer values from 0 through 905 and preserve rounded monthly patient-days. | Bed occupancy is a count, cannot exceed staffed capacity, and should remain consistent with the modeled monthly average. | Model design and executable validation |
| 2026-10-01 | Accept the validated 2017–2024 daily reconstruction as the historical modeling input. | The seeded generator produced 2,922 daily rows, a range of 480–779 occupied beds, maximum monthly mean error of 0.0171 bed, and positive daily persistence. | Notebook execution |
| 2026-10-01 | Impute 13 suppressed influenza LOS values by calendar-month median. | Retains broad seasonal structure without treating `***` as numeric; suppressed values remain explicitly flagged. | Notebook validation and documented assumption |
| 2026-10-01 | Restrict COVID-19 analysis to January 2020 through September 2024. | The 36 pre-2020 zeros precede the outbreak and represent unavailable/not-applicable observations; the three late-2024 months remain unavailable. | User constraint and notebook validation |
| 2026-10-01 | Do not impute unavailable COVID-19 months. | Ordinary seasonal imputation is not defensible for an evolving disease process. | Data inventory |
| 2026-10-01 | Accept the daily reconstruction as aligned with the monthly and clinical outputs. | Maximum monthly mean error is 0.0171 bed, full-period mean difference is 0.089 bed, 2024 mean difference is 0.0049 bed, and generated occupancy remains below 905 staffed beds. | Notebook cross-cell validation |
| 2026-10-01 | Split total VCU census across newborn, delivery, elective/non-elective, COVID-19, influenza, and other viral categories assuming an equal admission rate per category, with share proportional to LOS. | No category-level admission counts are available; this is the smallest defensible assumption that uses only existing LOS data. | User request and documented modeling assumption |
| 2026-10-01 | Derive free beds as staffed beds minus total occupied beds, at both monthly and daily resolution. | Directly answers how much capacity remains once modeled occupancy is removed. | Notebook execution |
| 2026-10-01 | Validate that category occupied-bed estimates sum back to total census every month. | Reconstruction error is at most 1.14e-13 bed, confirming the allocation is self-consistent. | Notebook validation |
| 2026-10-01 | Extend the AR(1) daily generator to each category and to intensive beds, reusing the total-census CV/persistence and capping at 905 staffed beds with a per-category seed offset. | No category-specific daily variability or bed-pool data exists; reuse is the smallest defensible extension of the validated total-census method. | Documented modeling assumption and notebook validation (max monthly-mean error 0.018 bed across all categories) |
| 2026-10-01 | Treat ICU as a peer section (ward), not a diagnosis subset; the 8 non-ICU categories now split only the non-ICU remainder so all 9 sections sum exactly to total census. | User clarified each category represents a hospital section (newborn, delivery, ICU, ER, surgery, etc.), correcting an earlier double-counting risk with ICU. | User clarification and notebook validation (reconstruction error 1.14e-13 bed) |
| 2026-10-01 | Replace independent per-category daily generation with allocation from the validated total daily series using each month's section share, reconciled to sum exactly to each day's total. | The independent approach did not sum to the daily total, contradicting the requirement that sections stay within the known total. | User clarification and notebook validation (section sum error 0.0) |
| 2026-10-01 | Add genuine day-to-day randomness to length of stay (AR(1), rescaled to the monthly mean) instead of repeating the monthly value. | User wants stay length to vary day to day while averaging back to the known monthly figure. | User clarification and notebook validation (LOS monthly mean error 0.0) |
| 2026-10-01 | Drop per-category "isolated" free-bed estimates; report only hospital-wide free beds. | User confirmed hospitals flexibly reassign ward capacity rather than reserving fixed per-category pools. | User clarification |
| 2026-10-01 | Scope the master daily dataset to January 2017–December 2024 in wide format, with COVID-19 shown as NaN where unavailable. | User decision; the 2025–2026 forecast is a separate step after this dataset is reviewed. | User clarification |
| 2026-10-01 | Replace the top-down allocate-then-split approach with an LOS-driven admissions/discharges turnover recurrence (Option B) per section; total occupied beds is now the sum of 9 sections. | User selected Option B so tomorrow's bed count depends on today's count and that section's current LOS, not independent draws. | User decision and notebook validation (reproducible, non-negative, 0 days over capacity, longer-LOS sections show higher day-to-day autocorrelation as expected) |
| 2026-10-01 | Accept approximate (not exact) monthly reconciliation under the turnover model; maximum category error 24.9 beds (influenza), mean error 3.0 beds across sections. | This is the expected cost of LOS-driven dynamics; volatile categories lag target shifts by about one LOS-cycle. | Notebook validation |
| 2026-10-01 | Fit a floor-asymptote exponential decay to post-peak COVID-19 occupancy and project October–December 2024 as a separate, clearly labeled column. | Observed data ends September 2024; the fit confirms a real large decline from a 169.65-bed December 2021 peak toward a 106.08-bed floor, never reaching zero. | Notebook curve fit (scipy.optimize.curve_fit) |
| 2026-10-01 | Flag that the single-wave decay fit ignores recurring winter waves and likely understates a December seasonal uptick. | The data shows repeated November/December bumps (e.g., ~126 beds Dec 2022, ~125 Nov 2023) that a pure decay-to-floor model cannot capture. | Visual inspection of the fitted chart |
| 2026-10-01 | Apply a calendar-month seasonal index (median of observed/trend per month, post-peak, renormalized to average 1) to the Oct-Dec 2024 COVID-19 projection. | Corrects the flat floor-only projection to reflect the recurring winter uptick; October/November/December indices of 1.058/1.130/1.167 raise the projection from 106.1 to 112.2/119.9/123.8 beds. | User feedback and notebook validation |
| 2026-10-01 | Fold the seasonally adjusted Oct-Dec 2024 COVID-19 projection into the master dataset: set it as the monthly target, proportionally shrink the other 6 non-ICU sections (ICU untouched) so all sections still sum to the known total, impute COVID-19 LOS for those 3 months via calendar-month seasonal median (2020+ window only), and regenerate COVID-19's daily LOS and turnover series. | Replaces NaN COVID-19 occupancy for Oct-Dec 2024 with a data-grounded estimate while keeping the total census and all other historical data unchanged. | User request and notebook validation (rebalance error 0.0, historical LOS reproduced bit-for-bit, 1,095 pre-2020 NaN rows correctly untouched, 0 days over capacity) |
| 2026-10-01 | Confirm no ICU-specific LOS can be derived from existing data; it is mathematically equivalent to the hospital-wide average under current assumptions. | Deriving an ICU LOS via the same admission-share logic used elsewhere algebraically collapses back to the constant overall LOS — it provides no new information. | Notebook-free mathematical derivation |
| 2026-10-01 | Estimate VCU intensive occupancy using Virginia's monthly intensive share. | Intensive occupancy is the only supplied subtype that is itself a bed census. | Documented modeling assumption |
| 2026-10-01 | Derive aggregate flow using 247,208 patient days and 41,852 discharges. | These observations imply 5.91 average LOS and about 114.6 daily discharges; steady-state admissions are set equal to discharges. | AHD data and notebook execution |
| 2026-10-01 | Defer occupied-bed estimates for LOS-only categories until volumes are available. | Occupancy requires admissions per day multiplied by LOS, and the categories overlap. | Data-readiness assessment |
