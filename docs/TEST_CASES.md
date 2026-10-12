# Test cases

Run everything: `python -m pytest -q` (unit, property and API tests) and
`python -m pytest tests/e2e -q` (browser smoke test). Status is from the last run on
2026-10-13: 103 unit/property/API tests and 1 end-to-end test, all passing.

## Edge cases

| ID | Scenario | Expected result | Test | Status |
|---|---|---|---|---|
| TC-01 | Zero combinations: two courses share their only slot | count 0, exact, plain message | `test_solver::test_zero_combinations_when_two_courses_share_their_only_slot` | Pass |
| TC-02 | Exactly one combination | that one combination, "1 combination available." | `test_solver::test_exactly_one_combination` | Pass |
| TC-03 | Very large number (5 lab courses) | capped, "at least M", every theory option represented, under 2 s | `test_solver::test_very_large_space_is_capped_honestly_and_spread_across_options` | Pass |
| TC-04 | All pins on one slot | zero combinations, both pins named | `test_solver::test_all_pins_on_one_slot_gives_zero`, `test_diagnostics::test_two_pins_on_the_same_cell` | Pass |
| TC-05 | Required course with a single slot | always placed in that slot | `test_solver::test_required_course_with_single_slot_is_always_in_that_slot` | Pass |
| TC-06 | Backlog course clashes with a required course | zero; message says the student cannot fix it; no removal offered | `test_diagnostics::test_backlog_clashing_with_required_is_not_fixable_by_the_student` | Pass |
| TC-07 | Credits exactly 16 | accepted | `test_solver::test_credit_limits_are_inclusive_at_16_and_27` | Pass |
| TC-08 | Credits exactly 27 | accepted; 15 and 28 refused with the number to add or remove | same test | Pass |
| TC-09 | Two students, identical preferences, same tier, one seat | order from the published seed; first gets 1st choice, second gets 2nd with the reason | `test_allocation::test_two_identical_students_same_tier_capacity_one` | Pass |
| TC-10 | Full course | student marked for add/drop, run does not fail | `test_allocation::test_full_course_marks_student_for_add_drop_instead_of_failing` | Pass |
| TC-11 | Capacity of 1 | never exceeded, in allocation and in add/drop | `test_allocation` property test, `test_api::test_add_drop_never_overbooks_a_full_slot` | Pass |
| TC-12 | Student changes preferences after submitting | new choices replace old; one stored row | `test_api::test_duplicate_submission_and_change_after_submitting` | Pass |
| TC-13 | Window closed (and not yet open) | submit and draft refused with a message; preview still works | `test_api::test_window_closed_and_not_yet_open` | Pass |
| TC-14 | Duplicate submission | no error, counted, one stored row | `test_api::test_duplicate_submission_and_change_after_submitting` | Pass |
| TC-15 | Invalid invite code | refused in plain words, logged | `test_api::test_invalid_and_expired_invite_codes_are_refused` | Pass |
| TC-16 | Expired invite code | refused, logged | same test | Pass |

## Other cases

| ID | Scenario | Expected result | Test | Status |
|---|---|---|---|---|
| TC-20 | Different slot names sharing a cell (`TC1`/`G1`) | clash | `test_clash::test_known_clashes` | Pass |
| TC-21 | Lab and theory on different clocks (`L2` vs `A1`) | clash; touching edges do not | `test_clash::test_known_clashes` | Pass |
| TC-22 | One slot name with several cells (`A1`) | all cells used | `test_clash::test_timetable_shape_matches_annexure_one` | Pass |
| TC-23 | Bit-mask clash equals interval overlap for every pair of slot names | identical | `test_clash::test_mask_agrees_with_interval_overlap_for_every_pair_of_slot_names` | Pass |
| TC-24 | Unknown slot name | error, never a silent "no clash" | `test_clash::test_unknown_slot_name_is_an_error_not_a_silent_no_clash` | Pass |
| TC-25 | Re-import of the PDFs | reproduces the committed catalogue exactly | `test_import::test_reimport_from_pdfs_reproduces_committed_catalogue` | Pass (skipped where PDFs are absent) |
| TC-26 | Pin applied before generation; lab pin; atom order | only that slot appears | `test_solver::test_pin_*` | Pass |
| TC-27 | Invalid pins (slot not offered, course not chosen, two pins on one course) | reported, not ignored | `test_solver::test_invalid_pins_are_reported_not_ignored` | Pass |
| TC-28 | Same inputs in a different order | identical output | `test_solver::test_same_inputs_same_output_regardless_of_input_order` | Pass |
| TC-29 | Solver equals brute force (property, 150 generated catalogues) | identical sets | `test_solver::test_solver_finds_exactly_the_conflict_free_combinations` | Pass |
| TC-30 | Every archetype rule; first match wins; catch-all required | as configured | `test_archetypes::test_classification_rules` and neighbours | Pass |
| TC-31 | Features and secondary score on a hand-built timetable; lunch is not a gap | exact values | `test_archetypes::test_features_of_a_hand_built_timetable`, `test_lunch_break_is_not_a_gap` | Pass |
| TC-32 | Conflict set is minimal (three-way clash, unrelated course left out) | 3 courses named | `test_diagnostics::test_conflict_set_is_minimal` | Pass |
| TC-33 | Relaxation unlock counts are true; one-click apply | re-solving gives the promised count | `test_diagnostics::test_relaxations_are_ranked_and_their_unlock_counts_are_true`, `test_api::test_impossible_pin_returns_diagnosis_with_one_click_fix_and_is_logged` | Pass |
| TC-34 | Drop not offered when it breaks the credit minimum | only the swap is offered | `test_diagnostics::test_drop_is_not_offered_when_it_breaks_the_credit_minimum` | Pass |
| TC-35 | Allocation never exceeds capacity and is deterministic (property, 120 cases) | holds | `test_allocation::test_allocation_never_exceeds_capacity_and_is_deterministic` | Pass |
| TC-36 | Tiers first; earlier misses move up; weight 0 turns it off | as described | `test_allocation::test_tiers_come_before_everything_else`, `test_students_who_missed_out_earlier_move_up_and_weight_is_configurable` | Pass |
| TC-37 | "Never" patterns are never assigned | holds | `test_allocation` property test | Pass |
| TC-38 | Dry run saves nothing; final run needs a closed window; same seed, same order | holds | `test_api::test_full_flow_dry_run_final_run_result_add_drop_and_exports` | Pass |
| TC-39 | Add/drop capped at one change; refused change does not use it up | holds | same test, `test_add_drop_never_overbooks_a_full_slot` | Pass |
| TC-40 | Simulation labelled synthetic, reproducible, saves nothing | holds | `test_allocation::test_simulation_on_the_real_catalogue_is_labelled_and_within_capacity`, `test_api::test_simulation_is_labelled_synthetic_and_saves_nothing` | Pass |
| TC-41 | Invite codes stored hashed; sign-in case-insensitive | holds | `test_api::test_invite_code_is_stored_hashed_and_signs_in` | Pass |
| TC-42 | Failed sign-ins rate-limited | 429 after 20 failures | `test_api::test_sign_in_attempts_are_rate_limited` | Pass |
| TC-43 | CSRF token required and checked | 403 without or with a wrong one | `test_api::test_csrf_header_is_required_and_must_match_the_session` | Pass |
| TC-44 | Students cannot reach admin; wrong admin secret refused | 403 / 401 | `test_api::test_no_session_no_data_and_student_cannot_reach_admin` | Pass |
| TC-45 | Malformed input (course code, pin, pattern, event, rating) | 422 | `test_api::test_input_validation` | Pass |
| TC-46 | Registration-number-like alias in a tester CSV | refused with a reason | `test_api::test_admin_testers_import_new_code_and_real_registration_numbers_refused` | Pass |
| TC-47 | Exports: results, feedback with SUS score, timing vs baseline, events; formulas neutralised | present | `test_api::test_full_flow_…` | Pass |
| TC-48 | Reset wipes beta data, keeps settings, takes a backup | holds | `test_api::test_reset_wipes_beta_data_keeps_settings_and_takes_a_backup` | Pass |
| TC-49 | Wording rule: banned words absent from code, config, UI and docs | none found | `test_api::test_wording_rule_holds_across_the_code_base` | Pass |
| TC-50 | Typical generation under 2 seconds | holds | `test_solver::test_typical_generation_is_under_two_seconds` | Pass |
| TC-51 | Student flow on a phone-sized screen, end to end | completes with a result and reason | `tests/e2e/test_student_flow.py` | Pass |
| TC-52 | 20 concurrent users | no failures | `tests/load/load_test.py`, see LOAD_TEST.md | Pass |

## Not covered by automated tests

- Touch drag-and-drop on a real phone (the arrows are tested; dragging is not).
- The Cloudflare tunnel and HTTPS cookie behaviour on a real device.
- Screen readers. Keyboard focus and labels are in place but were not audited.
- Admin PDF upload through the browser (the importer itself is tested).
