# Member Overview: metric definitions

Who our members are, how many are active, and how sign-ups are trending.

Generated from `app/metrics/patient_overview.yml`. Groups with fewer than 11 members are hidden.

## Measures

| Measure | Meaning | Rule | LookML source |
|---|---|---|---|
| Total members | Distinct members (patients) in the table. | `COUNT(DISTINCT patient.id)` | patient_gold_latest.unique_patient_count |
| Active members | Distinct members whose record is marked active in their program. | `COUNT(DISTINCT IF(COALESCE(patient.is_active, FALSE), patient.id, NULL))` | patient_gold_latest.active_patient_version_count |
| Active share | Active members divided by total members. | `SAFE_DIVIDE(COUNT(DISTINCT IF(COALESCE(patient.is_active, FALSE), patient.id, NULL)), COUNT(DISTINCT patient.id))` | derived (active_patient_version_count / unique_patient_count) |

## Dimensions

| Dimension | Meaning | Rule | LookML source |
|---|---|---|---|
| Organization | Human-readable name of the organization the member belongs to. | `patient.organization_compartment_name` | patient_gold_latest.organization_compartment_name |
| Care program | Name of the care program the member is enrolled in. | `patient.care_program_enrolled_healthcareservice_name` | patient_gold_latest.enrolled_healthcare_service |
| State | State from the member's address. | `patient.geographic_state` | patient_gold_latest.state |
| Age band | Age grouped into bands. Missing or negative ages are shown as Unknown. | `CASE WHEN patient.age IS NULL OR patient.age < 0 THEN 'Unknown' WHEN patient.age < 18 THEN 'Under 18' WHEN patient.age <= 29 THEN '18-29' WHEN patient.age <= 39 THEN '30-39' WHEN patient.age <= 49 THEN '40-49' WHEN patient.age <= 59 THEN '50-59' WHEN patient.age <= 69 THEN '60-69' ELSE '70+' END` | patient_gold_latest.age_bucket (bands copied; LookML computes age from a joined view) |
| Sex at birth | The member's assigned sex at birth. | `patient.birth_sex` | patient_gold_latest.birth_sex |
| Account status | Status of the member's Verily Me account. | `patient.verily_me_account_status` | patient_gold_latest.verily_me_account_status |
| Preferred language | Inferred preferred language code. | `patient.inferred_preferred_language_code` | patient_gold_latest.preferred_language |
| Cohort eligibility | Whether the member belongs to the cardiometabolic cohort group. | `CASE WHEN patient.group_id_list = 'lhs-cmb-cohort-group' THEN 'Cardiometabolic' ELSE 'None' END` | patient_gold_latest.cohort_eligibility |
| Sign-up month | Month the member's record was created. | `DATE_TRUNC(DATE(patient.created_at), MONTH)` | patient_gold_latest.created_at_month |

## Example questions

- How many members do we have, and how many are active? (uses: total_members, active_members, active_share)
- Which organizations have the most members? (uses: total_members, organization)
- Which organization or program has the highest share of active members? (uses: active_share, organization, care_program)
- Who are our members by age, sex and state? (uses: total_members, age_band, birth_sex, state)
- How are sign-ups trending month to month, and how many of those members are still active? (uses: total_members, active_members, signup_month)
- For one organization, how does the mix of programs, states and ages look? (uses: total_members, organization, care_program, state, age_band)
