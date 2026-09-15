export interface RuleGuideItem {
  simpleExplanation: string;
  exampleScenario: string;
  compliantExample: string;
  violationExample: string;
  actionToComply: string[];
}

/** Plain-language guidance for every executable rule in the rule packs. */
export const RULE_GUIDE_DATA: Record<string, RuleGuideItem> = {
  // =========================================================================
  // CODE ON WAGES, 2019
  // =========================================================================
  "WAGES.OVERTIME.RATE": {
    simpleExplanation:
      "When any employee works beyond normal shift hours, you must pay them overtime at double (2x) their normal wage rate. Overtime cannot be paid at regular single rates.",
    exampleScenario:
      "Worker Rajesh earns a basic hourly rate of ₹100/hr and works 6 hours of overtime in a week.",
    compliantExample:
      "Overtime rate is calculated at ₹200/hr (2 × ₹100). Rajesh receives ₹1,200 for his 6 overtime hours on his payslip.",
    violationExample:
      "Rajesh is paid at the ordinary ₹100/hr (₹600 total) or a flat 1.5x rate (₹150/hr), underpaying his statutory overtime entitlement.",
    actionToComply: [
      "Configure payroll to automatically compute overtime at 2.0x regular hourly wage.",
      "Track all overtime hours in the statutory overtime register.",
      "Disburse all overtime arrears in the same wage cycle.",
    ],
  },
  "WAGES.PERIOD.MAX_ONE_MONTH": {
    simpleExplanation:
      "Every employer must fix a wage payment cycle (daily, weekly, fortnightly, or monthly). Under no circumstances can a wage cycle exceed 31 days (one month).",
    exampleScenario:
      "A project company employs engineers and site staff on milestone contracts.",
    compliantExample:
      "Salaries are calculated and disbursed every 30 days on a regular monthly wage cycle.",
    violationExample:
      "Management settles wages every 45 or 60 days upon project milestone completions, violating the monthly ceiling.",
    actionToComply: [
      "Fix clear wage periods not exceeding 30 or 31 days in all employment contracts.",
      "Notify employees in writing of the official wage cycle.",
    ],
  },
  "WAGES.PAYMENT.MONTHLY_BY_SEVENTH": {
    simpleExplanation:
      "For employees paid on a monthly basis, salaries must be paid before the end of the 7th day of the following month.",
    exampleScenario:
      "Wages earned for work performed in the calendar month of October.",
    compliantExample:
      "Salary credits hit employees' bank accounts on or before November 7th.",
    violationExample:
      "Salaries are delayed until November 10th or 15th due to internal accounting approvals.",
    actionToComply: [
      "Finalize monthly attendance and payroll processing by the 3rd of each month.",
      "Execute bank disbursement files on or before the 7th day.",
    ],
  },
  "WAGES.PAYMENT.FINAL_SETTLEMENT": {
    simpleExplanation:
      "When a worker leaves employment (resignation, termination, retrenchment, or dismissal), their entire full and final settlement must be paid within 2 working days of exit.",
    exampleScenario:
      "An employee submits their resignation and works their final day on a Tuesday.",
    compliantExample:
      "All earned wages, leave encashment, and statutory dues are deposited into their account by Thursday (2 working days).",
    violationExample:
      "HR advises the departed worker to wait 45 to 60 days for their final settlement voucher.",
    actionToComply: [
      "Expedite exit clearance workflows between HR, IT, and Finance.",
      "Process settlement vouchers and execute bank transfers within 48 hours of exit.",
    ],
  },
  "WAGES.DEDUCTIONS.HALF_CAP": {
    simpleExplanation:
      "Total deductions made from an employee's salary in any month (for PF, insurance, advances, damages, or loans) must never exceed 50% of their total wages.",
    exampleScenario:
      "An employee earns ₹20,000 monthly. Deductions include PF (₹1,800), advance recovery (₹8,500), and transport (₹1,000) totaling ₹11,300.",
    compliantExample:
      "The employer caps total deductions at ₹10,000 (50% of ₹20,000) and defers the remaining ₹1,300 recovery to the next month.",
    violationExample:
      "Deducting the full ₹11,300 (56.5%), leaving the employee with less than half of their statutory monthly earnings.",
    actionToComply: [
      "Implement a hard 50% deduction ceiling check in your payroll software.",
      "Spread loan repayments over longer intervals if monthly recovery breaches the cap.",
    ],
  },
  "WAGES.REST_DAY.WEEKLY": {
    simpleExplanation:
      "Every worker is entitled to at least one full 24-hour day of rest in every period of 7 days, generally on Sunday or a substituted day of rest.",
    exampleScenario:
      "A 24/7 assembly line or data operations facility with continuous shifts.",
    compliantExample:
      "Each employee is given a designated weekly off (e.g. Wednesday or Sunday) after working 6 consecutive days.",
    violationExample:
      "Scheduling staff for 12 or 18 consecutive days during peak workloads without any scheduled day of rest.",
    actionToComply: [
      "Build shift rosters that guarantee at least one day off in every 7-day period.",
      "Maintain compensatory off registers if a worker is called in on their scheduled off.",
    ],
  },
  "WAGES.FLOOR.STATE_MINIMUM": {
    simpleExplanation:
      "You cannot pay any employee less than the official minimum wage set by the State Government for that specific skill level (unskilled, semi-skilled, skilled, highly skilled) and geographic zone.",
    exampleScenario:
      "The state government notifies a minimum daily wage of ₹450 (₹11,700/mo) for semi-skilled warehouse workers in Zone A.",
    compliantExample:
      "Warehouse workers are paid ₹480 per day (₹12,480/month), comfortably above the state minimum wage floor.",
    violationExample:
      "Paying workers ₹390 per day (₹10,140/month), which falls ₹60/day below the legally mandated state floor.",
    actionToComply: [
      "Review state gazette minimum wage revisions published in April and October.",
      "Update base salary structures immediately when minimum wage notifications are released.",
    ],
  },
  "WAGES.ARITHMETIC.GROSS": {
    simpleExplanation:
      "The Gross Pay column in your wage register must mathematically equal the exact sum of its components (Basic + DA + Allowances + Overtime).",
    exampleScenario:
      "A payslip shows Basic ₹12,000, DA ₹3,000, Overtime ₹2,000, and Allowance ₹1,500.",
    compliantExample:
      "Gross Wages is accurately recorded as exactly ₹18,500 (12,000 + 3,000 + 2,000 + 1,500).",
    violationExample:
      "Gross Wages is recorded as ₹17,000 due to a manual entry typo, causing an arithmetic audit discrepancy.",
    actionToComply: [
      "Use automated formula calculation in payroll registers instead of manual spreadsheet typing.",
      "Run automated register reconciliation before publishing salary statements.",
    ],
  },
  "WAGES.ARITHMETIC.NET": {
    simpleExplanation:
      "Net Wages paid to the employee must strictly equal Gross Wages minus Total Deductions. No unexplained gaps or unaccounted deductions are allowed.",
    exampleScenario:
      "An employee's gross wage is ₹25,000 and total statutory deductions (PF + ESI + PT) equal ₹2,350.",
    compliantExample:
      "The Net Pay transferred to the employee's bank account is exactly ₹22,650 (25,000 − 2,350).",
    violationExample:
      "Net pay is disbursed as ₹21,800, leaving ₹850 unaccounted for on the payroll register.",
    actionToComply: [
      "Ensure the payroll software derives Net Pay via strict formula: Gross − Deductions.",
      "Verify that the bank disbursement amount matches Net Pay to the rupee.",
    ],
  },
  "WAGES.HOURS.NORMAL_DAY_EIGHT": {
    simpleExplanation:
      "The uploaded wage record states normal daily hours above eight.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"normal_hours_per_day\": 8}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"normal_hours_per_day\": 10}]} — this is reported.",
    actionToComply: [
      "Correct the normal-hours record and treat qualifying additional work as overtime under the applicable rules.",
      "Cite and verify against Code on Wages (Central) Rules, 2026 — r.5.",
    ],
  },
  "WAGES.OVERTIME.AMOUNT_RECONCILES": {
    simpleExplanation:
      "The overtime amount in the uploaded record does not equal the recorded overtime hours multiplied by the recorded rate.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"overtime_hours\": 10, \"overtime_rate_paise\": 20000, \"overtime_paise\": 200000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"overtime_hours\": 10, \"overtime_rate_paise\": 20000, \"overtime_paise\": 100000}]} — this is reported.",
    actionToComply: [
      "Correct the hours, rate or overtime amount so the uploaded wage record reconciles.",
      "Cite and verify against Code on Wages, 2019 — s.14; Code on Wages (Central) Rules, 2026 — r.5.",
    ],
  },
  "WAGES.REGISTER.GROSS_RECORDED": {
    simpleExplanation:
      "Gross wages are blank for a worker in the uploaded wage record.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"gross_paise\": 1500000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"gross_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the gross-wage entry from the verified wage components.",
      "Cite and verify against Code on Wages, 2019 — s.50; Code on Wages (Central) Rules, 2026 — r.51 and Form IV.",
    ],
  },
  "WAGES.REGISTER.NET_RECORDED": {
    simpleExplanation:
      "Net wages are blank for a worker in the uploaded wage record.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"net_paid_paise\": 1300000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"net_paid_paise\": null}]} — this is reported.",
    actionToComply: [
      "Record the verified net amount paid after additions and deductions.",
      "Cite and verify against Code on Wages, 2019 — s.50; Code on Wages (Central) Rules, 2026 — r.51 and Form IV.",
    ],
  },
  "WAGES.REGISTER.PAYMENT_DATE_RECORDED": {
    simpleExplanation:
      "The payment date is blank for a worker in the uploaded wage record.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"paid_on\": \"2026-04-05\"}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"paid_on\": null}]} — this is reported.",
    actionToComply: [
      "Enter the actual verified payment date for the worker.",
      "Cite and verify against Code on Wages, 2019 — s.17 and s.50; Code on Wages (Central) Rules, 2026 — Form IV.",
    ],
  },
  "WAGES.REGISTER.DAYS_PAID_RECORDED": {
    simpleExplanation:
      "The number of paid days is blank for a worker in the uploaded wage record.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"wage_register\": [{\"days_paid\": 26}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"wage_register\": [{\"days_paid\": null}]} — this is reported.",
    actionToComply: [
      "Reconcile attendance and enter the verified number of days paid.",
      "Cite and verify against Code on Wages, 2019 — s.50; Code on Wages (Central) Rules, 2026 — r.51 and Form IV.",
    ],
  },
  "WAGES.DEFINITION.EXCLUDED_HALF_DEEMED_WAGES": {
    simpleExplanation:
      "Allowances excluded from wages exceed one half of total remuneration, so the excess is deemed to be wages and must be included in the statutory wage base.",
    exampleScenario:
      "This check runs whenever the records it needs are uploaded for the period.",
    compliantExample:
      "Example (allowances within half): {\"wage_register\": [{\"basic_paise\": 1200000, \"da_paise\": 300000, \"other_allowances_paise\": 500000}]} — this passes.",
    violationExample:
      "Example (allowances two thirds need addback): {\"wage_register\": [{\"basic_paise\": 400000, \"da_paise\": 100000, \"other_allowances_paise\": 1500000}]} — this is reported.",
    actionToComply: [
      "Add the excess above one half of remuneration into the statutory wage base used for contributions, gratuity and overtime, or restructure pay so excluded allowances stay within one half.",
      "Verify against Code on Wages, 2019 — s.2(y) proviso.",
    ],
  },
  // =========================================================================
  // INDUSTRIAL RELATIONS CODE, 2020
  // =========================================================================
  "IR.GRIEVANCE_COMMITTEE.SIZE_CAP": {
    simpleExplanation:
      "The Grievance Redressal Committee cannot exceed 10 members in total, keeping proceedings focused, effective, and balanced.",
    exampleScenario:
      "A large factory wants multiple department heads and trade union delegates on the committee.",
    compliantExample:
      "The factory restricts the committee to 8 or 10 members (e.g. 5 worker nominees and 5 management nominees).",
    violationExample:
      "Appointing 14 or 16 members to the committee, exceeding the statutory maximum limit of 10.",
    actionToComply: [
      "Cap the total committee strength at a maximum of 10 members.",
      "Ensure parity: 50% management representatives and 50% worker representatives.",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.WOMEN_REPRESENTATION": {
    simpleExplanation:
      "Women must be represented on the Grievance Redressal Committee in proportion to their share of the total workforce. If 40% of workers are women, at least 40% of worker representatives must be women.",
    exampleScenario:
      "A garment production unit employs 100 workers, of which 50 are women (50% female workforce). The committee has 6 worker seats.",
    compliantExample:
      "At least 3 out of the 6 worker representatives are women, matching the 50% workforce proportion.",
    violationExample:
      "Appointing only 1 female worker representative out of 6 (16.6%), falling well below the 50% female workforce representation.",
    actionToComply: [
      "Calculate the percentage of female employees in your establishment.",
      "Ensure women hold at least that proportion of seats on the committee.",
    ],
  },
  "IR.STRIKE.NOTICE_PERIOD": {
    simpleExplanation:
      "No worker may go on strike and no employer may declare a lock-out without giving at least 14 days' advance written notice. Wildcat or surprise strikes and sudden lockouts are strictly prohibited.",
    exampleScenario:
      "A trade union plans a strike over wage renegotiations.",
    compliantExample:
      "The union serves a formal written 14-day advance notice on October 1st for a strike starting October 16th, and notifies the conciliation officer.",
    violationExample:
      "Workers stage an immediate flash walkout without 14 days' notice, or management suddenly locks the gates overnight.",
    actionToComply: [
      "Ensure any strike or lock-out notice strictly respects the 14-day cooling period.",
      "Immediately transmit notices to the Conciliation Officer to start mediation.",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.EQUAL_REPRESENTATION": {
    simpleExplanation:
      "The uploaded committee record does not show equal employer and worker representation.",
    exampleScenario:
      "This check runs only when docs.grievance_committee_count > 0.",
    compliantExample:
      "Example (equal): {\"docs\": {\"grievance_committee_count\": 1}, \"prose\": {\"grievance_committee_employer_reps\": 4, \"grievance_committee_worker_reps\": 4}} — this passes.",
    violationExample:
      "Example (unequal): {\"docs\": {\"grievance_committee_count\": 1}, \"prose\": {\"grievance_committee_employer_reps\": 6, \"grievance_committee_worker_reps\": 2}} — this is reported.",
    actionToComply: [
      "Reconstitute and record the committee with equal employer and worker representation.",
      "Cite and verify against Industrial Relations Code, 2020 — s.4(2).",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.CHAIRPERSON_RECORDED": {
    simpleExplanation:
      "The uploaded committee record does not identify its chairperson.",
    exampleScenario:
      "This check runs only when docs.grievance_committee_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"grievance_committee_count\": 1}, \"prose\": {\"has_chairperson\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"grievance_committee_count\": 1}, \"prose\": {\"has_chairperson\": false}} — this is reported.",
    actionToComply: [
      "Record the chairperson selected in accordance with the alternating representation requirement.",
      "Cite and verify against Industrial Relations Code, 2020 — s.4(3).",
    ],
  },
  "IR.STRIKE.NOTICE_WITHIN_SIXTY_DAYS": {
    simpleExplanation:
      "The uploaded record places the strike or lock-out outside the permitted sixty-day notice window.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (within window): {\"prose\": {\"strike_notice_days\": 30}} — this passes.",
    violationExample:
      "Example (outside window): {\"prose\": {\"strike_notice_days\": 75}} — this is reported.",
    actionToComply: [
      "Issue a fresh notice and ensure the action occurs no earlier than fourteen and no later than sixty days after notice.",
      "Cite and verify against Industrial Relations Code, 2020 — s.62.",
    ],
  },
  "IR.STANDING_ORDERS.CERTIFIED_OR_MODEL": {
    simpleExplanation:
      "The uploaded standing orders do not show certification or adoption of the applicable model standing orders.",
    exampleScenario:
      "This check runs only when docs.standing_orders_count > 0.",
    compliantExample:
      "Example (certified): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"is_certified\": true, \"adopts_model_standing_orders\": false}} — this passes.",
    violationExample:
      "Example (neither): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"is_certified\": false, \"adopts_model_standing_orders\": false}} — this is reported.",
    actionToComply: [
      "Record adoption of the applicable model orders or obtain certification of differing standing orders.",
      "Cite and verify against Industrial Relations Code, 2020 — Chapter IV.",
    ],
  },
  "IR.STANDING_ORDERS.WORKER_CLASSIFICATION": {
    simpleExplanation:
      "The uploaded standing orders do not cover classification of workers.",
    exampleScenario:
      "This check runs only when docs.standing_orders_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_classification_of_workers\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_classification_of_workers\": false}} — this is reported.",
    actionToComply: [
      "Add the required worker classifications to the standing orders.",
      "Cite and verify against Industrial Relations Code, 2020 — First Schedule.",
    ],
  },
  "IR.STANDING_ORDERS.DISCIPLINARY_PROCEDURE": {
    simpleExplanation:
      "The uploaded standing orders do not describe the disciplinary procedure.",
    exampleScenario:
      "This check runs only when docs.standing_orders_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_disciplinary_procedure\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_disciplinary_procedure\": false}} — this is reported.",
    actionToComply: [
      "Add misconduct, disciplinary-process and worker-redress provisions.",
      "Cite and verify against Industrial Relations Code, 2020 — First Schedule.",
    ],
  },
  "IR.STANDING_ORDERS.TERMINATION_TERMS": {
    simpleExplanation:
      "The uploaded standing orders do not state termination and notice conditions.",
    exampleScenario:
      "This check runs only when docs.standing_orders_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_termination\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"standing_orders_count\": 1}, \"prose\": {\"covers_termination\": false}} — this is reported.",
    actionToComply: [
      "Add the applicable termination and notice conditions.",
      "Cite and verify against Industrial Relations Code, 2020 — First Schedule.",
    ],
  },
  // =========================================================================
  // CODE ON SOCIAL SECURITY, 2020
  // =========================================================================
  "SS.EPF.WORKERS_NOT_COVERED": {
    simpleExplanation:
      "Every eligible employee listed on the wage register in an EPF-covered establishment must be enrolled in the Employees' Provident Fund and included in the monthly ECR return.",
    exampleScenario:
      "A company with 35 workers prepares its monthly payroll.",
    compliantExample:
      "All 35 workers are enrolled with Universal Account Numbers (UANs) and reflected in the EPFO Electronic Challan cum Return (ECR).",
    violationExample:
      "Depositing PF for only 20 employees while leaving 15 workers off the PF return by labeling them casual staff.",
    actionToComply: [
      "Audit your employee master list against monthly EPFO ECR returns.",
      "Generate UANs and enroll every eligible worker from their first day of work.",
    ],
  },
  "SS.EPF.WAGE_BASE_UNDERSTATED": {
    simpleExplanation:
      "The wage base used to compute EPF contributions (Basic + DA + Retaining Allowance) must not be artificially depressed or disguised as excessive non-statutory allowances.",
    exampleScenario:
      "An employee earns ₹14,000 monthly (Basic ₹10,000 + DA ₹4,000).",
    compliantExample:
      "PF is calculated on the full statutory wage base of ₹14,000 (12% = ₹1,680).",
    violationExample:
      "Splitting the salary into Basic ₹4,000 and 'Special Allowance' ₹10,000, and deducting PF on only ₹4,000 (12% = ₹480) to evade contributions.",
    actionToComply: [
      "Ensure the PF wage base includes Basic + DA in accordance with the 50% statutory rule.",
      "Review pay structures to prevent artificial reduction of PF-qualifying wages.",
    ],
  },
  "SS.HEADCOUNT.RECONCILIATION": {
    simpleExplanation:
      "The total worker count declared across your internal wage register, monthly EPF return, ESIC return, and statutory annual return must reconcile cleanly.",
    exampleScenario:
      "An industrial firm reviews its multi-department labour records.",
    compliantExample:
      "The wage register shows 48 active staff, and both the EPF and annual returns report the same 48 workers.",
    violationExample:
      "The wage register lists 48 workers, the EPF filing shows 32 workers, and the annual return states 40 workers without explanation.",
    actionToComply: [
      "Conduct monthly headcount reconciliation across HR, payroll, and statutory filings.",
      "Document justifications for any non-covered staff (e.g. wages above statutory ceilings).",
    ],
  },
  "SS.EPF.WAGE_BASE_RECORDED": {
    simpleExplanation:
      "The uploaded EPF record has a member row with no contribution wage base.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"epf\": [{\"wage_base_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"epf\": [{\"wage_base_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified EPF contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter III and prescribed contribution return.",
    ],
  },
  "SS.EPF.EMPLOYEE_SHARE_RECORDED": {
    simpleExplanation:
      "The uploaded EPF record has a member row with no employee contribution amount.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"epf\": [{\"employee_share_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"epf\": [{\"employee_share_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified EPF contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter III and prescribed contribution return.",
    ],
  },
  "SS.EPF.EMPLOYER_SHARE_RECORDED": {
    simpleExplanation:
      "The uploaded EPF record has a member row with no employer contribution amount.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"epf\": [{\"employer_share_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"epf\": [{\"employer_share_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified EPF contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter III and prescribed contribution return.",
    ],
  },
  "SS.ESIC.WAGE_BASE_RECORDED": {
    simpleExplanation:
      "The uploaded ESIC record has a member row with no contribution wage base.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"esic\": [{\"wage_base_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"esic\": [{\"wage_base_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified ESIC contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter IV and prescribed contribution return.",
    ],
  },
  "SS.ESIC.EMPLOYEE_SHARE_RECORDED": {
    simpleExplanation:
      "The uploaded ESIC record has a member row with no employee contribution amount.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"esic\": [{\"employee_share_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"esic\": [{\"employee_share_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified ESIC contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter IV and prescribed contribution return.",
    ],
  },
  "SS.ESIC.EMPLOYER_SHARE_RECORDED": {
    simpleExplanation:
      "The uploaded ESIC record has a member row with no employer contribution amount.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"esic\": [{\"employer_share_paise\": 100000}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"esic\": [{\"employer_share_paise\": null}]} — this is reported.",
    actionToComply: [
      "Complete the verified ESIC contribution particulars in the applicable return.",
      "Cite and verify against Code on Social Security, 2020 — Chapter IV and prescribed contribution return.",
    ],
  },
  // =========================================================================
  // OCCUPATIONAL SAFETY, HEALTH AND WORKING CONDITIONS CODE, 2020
  // =========================================================================
  "OSH.CONTRACTOR.LICENCE_VALID": {
    simpleExplanation:
      "Any contractor supplying 50 or more workers must hold a valid contract labour licence. Principal employers must verify the contractor's licence before engaging contract labour.",
    exampleScenario:
      "A warehouse engages a security and housekeeping agency supplying 60 contract staff.",
    compliantExample:
      "The principal employer verifies and archives a copy of the contractor's valid labour licence before allowing workers on site.",
    violationExample:
      "Engaging contract workers through an agency whose labour licence expired 6 months ago or was never obtained.",
    actionToComply: [
      "Audit contractor compliance quarterly and collect renewal licence copies.",
      "Refuse deployment from contractors whose statutory licences have lapsed.",
    ],
  },
  "OSH.CONTRACTOR.LICENCE_HEADCOUNT": {
    simpleExplanation:
      "A contractor cannot deploy more contract workers than the maximum headcount authorized in their licence. Deploying excess workers is illegal.",
    exampleScenario:
      "A contractor holds a licence permitting deployment of up to 40 workers.",
    compliantExample:
      "The contractor deploys 35 workers at the principal employer's site.",
    violationExample:
      "The contractor deploys 65 workers under a licence capped at 40 workers without applying for a headcount amendment.",
    actionToComply: [
      "Check daily contractor muster rolls against the licence headcount limit.",
      "Instruct the contractor to file for an amendment if additional manpower is required.",
    ],
  },
  "OSH.ACCIDENT.NOTIFIED": {
    simpleExplanation:
      "Any workplace accident causing death or bodily injury preventing an employee from working for 48 hours or more must be formally reported to the Inspector-cum-Facilitator.",
    exampleScenario:
      "A shop-floor technician suffers a burn that requires 4 days of hospital treatment and sick leave.",
    compliantExample:
      "The safety officer enters the injury in the accident register and sends a formal accident report to the labour authority.",
    violationExample:
      "Recording the accident in internal clinic logs but failing to notify the government labour inspector.",
    actionToComply: [
      "Maintain a comprehensive Accident Register on site.",
      "Send statutory accident notifications to the Inspector-cum-Facilitator for any absence exceeding 48 hours.",
    ],
  },
  "OSH.HOURS.WEEKLY_CAP": {
    simpleExplanation:
      "Normal weekly working hours for any adult worker must not exceed 48 hours in any week, regardless of how daily shifts are arranged.",
    exampleScenario:
      "A company schedules workers for 6 working days per week.",
    compliantExample:
      "Workers work 8 hours per day for 6 days = 48 hours total for the week.",
    violationExample:
      "Scheduling staff for 10 hours per day for 6 days (60 hours/week) on normal basic wages without overtime.",
    actionToComply: [
      "Cap standard weekly schedules at 48 normal working hours.",
      "Audit weekly timesheets to ensure no worker exceeds the statutory threshold.",
    ],
  },
  "OSH.ATTENDANCE.DAYS_PAID_MATCH": {
    simpleExplanation:
      "The number of days for which wages are paid in the salary register must match the number of days the worker was marked present on the attendance register/biometric punch.",
    exampleScenario:
      "A technician's biometric attendance logs 26 days of physical presence in the month.",
    compliantExample:
      "The salary register calculates pay for all 26 present days plus paid statutory weekly rest days.",
    violationExample:
      "The muster roll shows 26 days present, but payroll calculates wages for only 21 days without any authorized deduction.",
    actionToComply: [
      "Reconcile biometric attendance logs directly with the payroll calculation system.",
      "Ensure all present days and approved paid leaves are credited.",
    ],
  },
  "OSH.OVERTIME.HOURS_PAID": {
    simpleExplanation:
      "Whenever extra hours are logged in the attendance register or overtime book, corresponding overtime pay must appear on the wage register. Unpaid overtime is strictly illegal.",
    exampleScenario:
      "Biometric logs show a worker performed 12 hours of overtime work during the month.",
    compliantExample:
      "The worker's wage slip includes a dedicated line item showing 12 overtime hours paid at double rates.",
    violationExample:
      "Timesheets show 12 overtime hours worked, but the wage register shows ₹0 overtime payment.",
    actionToComply: [
      "Cross-check overtime logs against monthly wage registers prior to pay distribution.",
      "Ensure every recorded overtime hour generates double-rate compensation.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.EMPLOYEE_NAME": {
    simpleExplanation:
      "The uploaded appointment letter does not state the employee name.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_employee_name\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_employee_name\": false}} — this is reported.",
    actionToComply: [
      "Record the employee's name in the appointment letter.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.DESIGNATION": {
    simpleExplanation:
      "The uploaded appointment letter does not state the designation or post.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_designation\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_designation\": false}} — this is reported.",
    actionToComply: [
      "Add the employee's designation or post.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.JOINING_DATE": {
    simpleExplanation:
      "The uploaded appointment letter does not state the date of joining.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_date_of_joining\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_date_of_joining\": false}} — this is reported.",
    actionToComply: [
      "Add the verified date of joining.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.WAGE_RATE": {
    simpleExplanation:
      "The uploaded appointment letter does not state the wage or salary.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_wage_rate\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_wage_rate\": false}} — this is reported.",
    actionToComply: [
      "Add the wage or salary payable.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.WORKING_HOURS": {
    simpleExplanation:
      "The uploaded appointment letter does not state the working hours.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_working_hours\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_working_hours\": false}} — this is reported.",
    actionToComply: [
      "Add the applicable daily or weekly working hours.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.EMPLOYER_SIGNATURE": {
    simpleExplanation:
      "The uploaded appointment letter does not state the employer signature or authentication.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (uploaded record complies): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"is_signed_by_employer\": true}} — this passes.",
    violationExample:
      "Example (uploaded record is incomplete): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"is_signed_by_employer\": false}} — this is reported.",
    actionToComply: [
      "Have the appointment letter signed or authenticated on behalf of the employer.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
  "OSH.ACCIDENT.NOTIFICATION_REFERENCE": {
    simpleExplanation:
      "An uploaded accident row gives a notification date but no notification reference.",
    exampleScenario:
      "This check runs whenever the required records are uploaded for the period.",
    compliantExample:
      "Example (compliant record): {\"incidents\": [{\"notified_on\": \"2026-03-05\", \"notification_reference\": \"NOTICE-12\"}]} — this passes.",
    violationExample:
      "Example (non compliant record): {\"incidents\": [{\"notified_on\": \"2026-03-05\", \"notification_reference\": null}]} — this is reported.",
    actionToComply: [
      "Record the authority notification reference against the accident entry.",
      "Cite and verify against OSH & Working Conditions Code, 2020 — s.10; OSHWC (Central) Rules, 2026 — r.7.",
    ],
  },
  "OSH.HOURS.BEYOND_NORMAL_DAY_NOT_OVERTIME": {
    simpleExplanation:
      "A worker was recorded working more than the eight-hour normal working day on at least one day, but no overtime hours are recorded for that worker.",
    exampleScenario:
      "This check runs whenever the records it needs are uploaded for the period.",
    compliantExample:
      "Example (nine hour day recorded as overtime): {\"attendance\": [{\"max_daily_hours\": 9, \"overtime_hours\": 6}]} — this passes.",
    violationExample:
      "Example (thirteen hour day without overtime): {\"attendance\": [{\"max_daily_hours\": 13.5, \"overtime_hours\": 0}]} — this is reported.",
    actionToComply: [
      "Record every hour worked beyond the eight-hour normal day as overtime and pay it at not less than twice the ordinary rate.",
      "Verify against OSH & Working Conditions Code, 2020 — s.25; OSHWC (Central) Rules, 2026 — r.69.",
    ],
  },
};
