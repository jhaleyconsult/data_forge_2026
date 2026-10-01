USE "data_forge";

CREATE SCHEMA IF NOT EXISTS "Hospital";

CREATE SEQUENCE "Hospital"."new_table_id_seq" START 1;

CREATE TABLE "Hospital"."daily_totals" (
    id BIGINT PRIMARY KEY DEFAULT nextval('Hospital.new_table_id_seq'),
    "date" DATE,
    total_staffed_beds BIGINT,
    total_occupied_beds BIGINT,
    total_free_beds BIGINT,
    occupied_beds_newborn BIGINT,
    occupied_beds_delivery BIGINT,
    occupied_beds_non_elective_via_ed BIGINT,
    occupied_beds_non_elective_other BIGINT,
    occupied_beds_elective BIGINT,
    occupied_beds_covid_19 BIGINT,
    occupied_beds_influenza BIGINT,
    occupied_beds_other_viral BIGINT,
    occupied_beds_intensive BIGINT,
    admissions_newborn BIGINT,
    admissions_delivery BIGINT,
    admissions_non_elective_via_ed BIGINT,
    admissions_non_elective_other BIGINT,
    admissions_elective BIGINT,
    admissions_covid_19 BIGINT,
    admissions_influenza BIGINT,
    admissions_other_viral BIGINT,
    admissions_intensive BIGINT,
    expected_discharges_newborn DOUBLE,
    expected_discharges_delivery DOUBLE,
    expected_discharges_non_elective_via_ed DOUBLE,
    expected_discharges_non_elective_other DOUBLE,
    expected_discharges_elective DOUBLE,
    expected_discharges_covid_19 DOUBLE,
    expected_discharges_influenza DOUBLE,
    expected_discharges_other_viral DOUBLE,
    expected_discharges_intensive DOUBLE,
    avg_los_newborn_days DOUBLE,
    avg_los_delivery_days DOUBLE,
    avg_los_non_elective_via_ed_days DOUBLE,
    avg_los_non_elective_other_days DOUBLE,
    avg_los_elective_days DOUBLE,
    avg_los_covid_19_days DOUBLE,
    avg_los_influenza_days DOUBLE,
    avg_los_other_viral_days DOUBLE
);


USE "data_forge";

INSERT INTO "Hospital"."daily_totals" BY NAME
SELECT *
FROM read_csv_auto('data/vcu_master_daily.csv', header = true);