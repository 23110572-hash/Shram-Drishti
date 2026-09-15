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
      "Every worker is entitled to at least one full 24 hour day of rest in every period of 7 days, generally on Sunday or a substituted day of rest.",
    exampleScenario:
      "A 24/7 assembly line or data operations facility with continuous shifts.",
    compliantExample:
      "Each employee is given a designated weekly off (e.g. Wednesday or Sunday) after working 6 consecutive days.",
    violationExample:
      "Scheduling staff for 12 or 18 consecutive days during peak workloads without any scheduled day of rest.",
    actionToComply: [
      "Build shift rosters that guarantee at least one day off in every 7 day period.",
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
      "Normal daily working hours for adult employees must not exceed 8 hours per day, excluding statutory intervals of rest.",
    exampleScenario:
      "A manufacturing facility plans its standard production shift timings.",
    compliantExample:
      "Workers are rostered for an 8 hour daily shift (e.g., 9:00 AM to 5:00 PM) plus a scheduled 30 minute lunch break.",
    violationExample:
      "Workers are scheduled for 10 regular hours daily without recording the extra 2 hours as overtime.",
    actionToComply: [
      "Ensure regular daily shift schedules do not exceed 8 hours per day.",
      "Record any additional work beyond 8 hours as overtime with 2x compensatory pay.",
    ],
  },
  "WAGES.OVERTIME.AMOUNT_RECONCILES": {
    simpleExplanation:
      "The total overtime pay in the wage register must accurately reconcile with the recorded overtime hours multiplied by the overtime rate.",
    exampleScenario:
      "A technician completes 10 hours of overtime at a rate of ₹200/hr (total statutory entitlement ₹2,000).",
    compliantExample:
      "The wage register credits ₹2,000 for 10 overtime hours, exactly matching 10 hrs × ₹200/hr.",
    violationExample:
      "The wage register records 10 overtime hours at ₹200/hr but only credits ₹1,000, leaving a ₹1,000 discrepancy.",
    actionToComply: [
      "Audit payroll calculations to ensure overtime hours multiplied by overtime rate equals total overtime pay.",
      "Rectify any discrepancies in the wage register before releasing payment disbursements.",
    ],
  },
  "WAGES.REGISTER.GROSS_RECORDED": {
    simpleExplanation:
      "Gross wages must be explicitly recorded for every employee in the statutory wage register.",
    exampleScenario:
      "Generating monthly wage register entries across factory and warehouse staff.",
    compliantExample:
      "Every employee record displays their calculated gross wage (e.g. ₹15,000) combining basic, DA, and allowances.",
    violationExample:
      "Gross wage column is left blank or null for employees on the register.",
    actionToComply: [
      "Ensure every employee entry in Form IV includes calculated gross wages.",
      "Validate automated payroll exports to eliminate blank wage entries.",
    ],
  },
  "WAGES.REGISTER.NET_RECORDED": {
    simpleExplanation:
      "The net wages paid to each worker after statutory and authorized deductions must be explicitly recorded.",
    exampleScenario:
      "Finalizing monthly wage register payouts and bank disbursement statements.",
    compliantExample:
      "The register specifies the exact net amount paid (e.g. ₹13,000 after deductions) for each worker.",
    violationExample:
      "The net wage column is omitted or left unrecorded, obscuring the actual amount paid.",
    actionToComply: [
      "Record the verified net amount paid after all authorized deductions for every worker.",
      "Reconcile net pay figures with bank salary transfer sheets.",
    ],
  },
  "WAGES.REGISTER.PAYMENT_DATE_RECORDED": {
    simpleExplanation:
      "The actual date on which wages were disbursed must be explicitly recorded for every employee.",
    exampleScenario:
      "Monthly salary disbursement cycle across permanent and contract workers.",
    compliantExample:
      "The wage register records the exact payment date (e.g. 5th April 2026) for each employee.",
    violationExample:
      "The payment date column is left blank or unrecorded in the wage register.",
    actionToComply: [
      "Enter the actual disbursement date for every employee entry in the wage register.",
      "Retain timestamped bank transfer confirmations to support the recorded payment dates.",
    ],
  },
  "WAGES.REGISTER.DAYS_PAID_RECORDED": {
    simpleExplanation:
      "The total number of days for which wages are paid in the wage period must be explicitly recorded in the register.",
    exampleScenario:
      "Calculating monthly employee salaries based on verified attendance records.",
    compliantExample:
      "The wage register states 26 days paid based on attendance and authorized paid leaves.",
    violationExample:
      "The days paid column is left blank or missing on the statutory wage register.",
    actionToComply: [
      "Reconcile biometric attendance and muster rolls to record total paid days for each worker.",
      "Ensure total days paid includes earned leave, festival holidays, and working days.",
    ],
  },
  "WAGES.DEFINITION.EXCLUDED_HALF_DEEMED_WAGES": {
    simpleExplanation:
      "Excluded allowances (such as HRA, conveyance, and bonus) must not exceed 50% of total remuneration. Any excess beyond 50% is deemed to be wages for statutory benefits.",
    exampleScenario:
      "A compensation package pays Basic ₹12,000, DA ₹3,000, and Special Allowances ₹5,000 (total ₹20,000).",
    compliantExample:
      "Excluded allowances (₹5,000) are 25% of total remuneration, well within the 50% statutory threshold.",
    violationExample:
      "Salary is split into Basic ₹4,000 and allowances ₹16,000 (80%), artificially minimizing the base for PF and gratuity.",
    actionToComply: [
      "Structure salary compensation so basic pay and DA make up at least 50% of total CTC.",
      "Include any allowance amounts exceeding 50% in the statutory wage base for PF, ESI, and gratuity.",
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
      "The union serves a formal written 14 day advance notice on October 1st for a strike starting October 16th, and notifies the conciliation officer.",
    violationExample:
      "Workers begin a lightning strike with only 3 days' advance notice during active wage discussions.",
    actionToComply: [
      "Ensure any strike or lock-out notice strictly respects the 14 day cooling period.",
      "Immediately transmit notices to the Conciliation Officer to start mediation.",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.EQUAL_REPRESENTATION": {
    simpleExplanation:
      "The Grievance Redressal Committee must have equal representation of employer and worker nominees.",
    exampleScenario:
      "An industrial establishment with 20 or more workers constitutes a Grievance Redressal Committee.",
    compliantExample:
      "The committee comprises 4 employer representatives and 4 worker representatives, maintaining parity.",
    violationExample:
      "The committee has 6 employer representatives and only 2 worker representatives.",
    actionToComply: [
      "Ensure the Grievance Redressal Committee maintains an equal 50:50 ratio of employer and worker nominees.",
      "Record committee nominations and official member lists in establishment records.",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.CHAIRPERSON_RECORDED": {
    simpleExplanation:
      "The Grievance Redressal Committee must record a designated chairperson, alternating annually between employer and worker representatives.",
    exampleScenario:
      "Annual reorganization and chair appointment for the Grievance Redressal Committee.",
    compliantExample:
      "The committee formally designates a chairperson, alternating between worker and management representatives each year.",
    violationExample:
      "The committee operates without a designated chairperson or never alternates the role to worker representatives.",
    actionToComply: [
      "Formally designate and record the chairperson in Grievance Redressal Committee records.",
      "Ensure the role of chairperson alternates annually between employer and worker representatives.",
    ],
  },
  "IR.STRIKE.NOTICE_WITHIN_SIXTY_DAYS": {
    simpleExplanation:
      "A strike or lock-out must commence within 60 days of giving statutory notice. Actions initiated after 60 days require a fresh notice.",
    exampleScenario:
      "A registered trade union issues formal notice of industrial action.",
    compliantExample:
      "The strike commences 20 days after notice is served, falling within the permitted 14 to 60 day legal window.",
    violationExample:
      "Commencing industrial action 75 days after the notice was served without giving a fresh 14 day notice.",
    actionToComply: [
      "Track strike/lock-out validity strictly between day 15 and day 60 post-notice.",
      "Issue a fresh notice if negotiations extend beyond the 60 day validity window.",
    ],
  },
  "IR.STANDING_ORDERS.CERTIFIED_OR_MODEL": {
    simpleExplanation:
      "Establishments with 300 or more workers must either adopt Model Standing Orders or obtain certified Standing Orders governing conditions of service.",
    exampleScenario:
      "A plant employing 350 workers establishes formal service and conduct rules.",
    compliantExample:
      "The establishment formally adopts the Central Model Standing Orders or obtains certification from the Certifying Officer.",
    violationExample:
      "Operating a facility of 350 workers under informal, uncertified internal company rules.",
    actionToComply: [
      "Formally adopt the Model Standing Orders under the Industrial Relations Code.",
      "Submit custom draft standing orders to the Certifying Officer for formal certification if applicable.",
    ],
  },
  "IR.STANDING_ORDERS.WORKER_CLASSIFICATION": {
    simpleExplanation:
      "Standing Orders must explicitly classify workers into defined statutory categories such as permanent, probationer, temporary, fixed-term, and apprentice.",
    exampleScenario:
      "Drafting terms of employment and job classifications for establishment staff.",
    compliantExample:
      "Standing orders explicitly define categories for permanent staff, probationers, fixed-term employees, and apprentices.",
    violationExample:
      "Classifying all workers ambiguously as general staff without defining service categories or probation terms.",
    actionToComply: [
      "Include defined worker classifications (permanent, probationer, temporary, fixed-term) in standing orders.",
      "Align employment letters and contracts with these statutory classifications.",
    ],
  },
  "IR.STANDING_ORDERS.DISCIPLINARY_PROCEDURE": {
    simpleExplanation:
      "Standing Orders must clearly define acts of misconduct, disciplinary inquiry procedures, suspension rules, and penalties.",
    exampleScenario:
      "Establishing disciplinary guidelines and domestic inquiry standards for the workplace.",
    compliantExample:
      "Standing orders outline defined acts of misconduct, notice periods, hearing rights, and fair inquiry processes.",
    violationExample:
      "Disciplining or dismissing workers without documented domestic inquiry procedures or defined misconduct rules.",
    actionToComply: [
      "Document clear misconduct definitions and written domestic inquiry procedures in standing orders.",
      "Ensure procedures adhere to principles of natural justice, including right to be heard and show-cause notice.",
    ],
  },
  "IR.STANDING_ORDERS.TERMINATION_TERMS": {
    simpleExplanation:
      "Standing Orders must clearly set out notice periods and terms governing termination of employment and separation.",
    exampleScenario:
      "Defining statutory separation and retrenchment terms in workplace regulations.",
    compliantExample:
      "Standing orders detail one month's notice or payment in lieu, alongside statutory retrenchment compensations.",
    violationExample:
      "Standing orders allow summary termination without notice, hearing, or statutory severance provisions.",
    actionToComply: [
      "Detail statutory notice periods (e.g. 30 days) and severance terms in standing orders.",
      "Ensure termination terms align with Chapter IX and Section 70 of the Industrial Relations Code.",
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
      "The monthly EPFO electronic return (ECR) must explicitly declare the statutory PF qualifying wage base (Basic + DA) for every covered worker.",
    exampleScenario:
      "Preparing monthly PF contribution statements for establishment staff.",
    compliantExample:
      "The electronic return specifies each worker's statutory PF wage base (e.g. ₹15,000) for calculation.",
    violationExample:
      "The PF wage base column is left blank or zero on the electronic challan return.",
    actionToComply: [
      "Declare the exact statutory PF wage base for every enrolled worker on the monthly ECR return.",
      "Verify that basic wage and dearness allowance are correctly included in the PF wage base.",
    ],
  },
  "SS.EPF.EMPLOYEE_SHARE_RECORDED": {
    simpleExplanation:
      "The employee's 12% PF contribution deduction must be explicitly recorded in the monthly EPF return.",
    exampleScenario:
      "Reconciling monthly employee payroll deductions against EPFO remittances.",
    compliantExample:
      "The monthly ECR return records the exact employee deduction of ₹1,800 on a ₹15,000 wage base.",
    violationExample:
      "Employee contribution figures are left blank or zero for active enrolled workers.",
    actionToComply: [
      "Record the verified 12% employee deduction for every member on the monthly EPFO return.",
      "Ensure deductions in the return match the amounts deducted on employee pay slips.",
    ],
  },
  "SS.EPF.EMPLOYER_SHARE_RECORDED": {
    simpleExplanation:
      "The employer's matching PF contribution (allocated between EPF and EPS) must be explicitly recorded in the monthly EPF return.",
    exampleScenario:
      "Calculating monthly employer statutory contributions for covered workforce.",
    compliantExample:
      "The return records the employer contribution (3.67% EPF + 8.33% EPS, total 12%) for each worker.",
    violationExample:
      "The employer contribution column is left blank or missing on the electronic return.",
    actionToComply: [
      "Compute and record the employer matching contribution (8.33% EPS and 3.67% EPF) for each member.",
      "Ensure total remitted amounts correspond with bank payment challans.",
    ],
  },
  "SS.ESIC.WAGE_BASE_RECORDED": {
    simpleExplanation:
      "The monthly ESIC return must declare the total insurable gross wages for every covered employee earning up to ₹21,000 per month.",
    exampleScenario:
      "Filing monthly health insurance contribution returns on the ESIC portal.",
    compliantExample:
      "Gross monthly wages (e.g. ₹18,000) are accurately declared for each insured employee.",
    violationExample:
      "Insurable wage values are submitted as blank or zero for active covered employees.",
    actionToComply: [
      "Declare the total insurable gross wage earned by each covered employee in the monthly ESIC return.",
      "Verify that all earnings except annual bonus and travelling allowance are included in insurable wages.",
    ],
  },
  "SS.ESIC.EMPLOYEE_SHARE_RECORDED": {
    simpleExplanation:
      "The employee's 0.75% ESIC contribution deduction must be explicitly recorded in the monthly ESIC return.",
    exampleScenario:
      "Processing monthly salary deductions for employees covered under ESIC.",
    compliantExample:
      "The return records the statutory 0.75% employee deduction (e.g. ₹135 on an ₹18,000 wage base).",
    violationExample:
      "The employee contribution column is left blank or zero for covered staff.",
    actionToComply: [
      "Record the statutory 0.75% deduction for each covered employee in the ESIC monthly filing.",
      "Verify that employee deductions reconcile exactly with payroll wage register entries.",
    ],
  },
  "SS.ESIC.EMPLOYER_SHARE_RECORDED": {
    simpleExplanation:
      "The employer's 3.25% ESIC contribution must be explicitly recorded and remitted in the monthly ESIC return.",
    exampleScenario:
      "Depositing monthly employer social health insurance contributions.",
    compliantExample:
      "The return records the employer contribution of 3.25% (e.g. ₹585 on an ₹18,000 wage base) for each employee.",
    violationExample:
      "The employer contribution is omitted or left unrecorded on the monthly filing.",
    actionToComply: [
      "Calculate and record the 3.25% employer contribution for every covered employee.",
      "Remit the total combined 4% ESIC contribution before the 15th of the following month.",
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
      "Any workplace accident causing death or bodily injury preventing an employee from working for 48 hours or more must be formally reported to the Inspector.",
    exampleScenario:
      "A shop-floor technician suffers a burn that requires 4 days of hospital treatment and sick leave.",
    compliantExample:
      "The safety officer enters the injury in the accident register and sends a formal accident report to the labour authority.",
    violationExample:
      "Recording the accident in internal clinic logs but failing to notify the government labour inspector.",
    actionToComply: [
      "Maintain a comprehensive Accident Register on site.",
      "Send statutory accident notifications to the Inspector for any absence exceeding 48 hours.",
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
  "OSH.ACCIDENT.NOTIFICATION_REFERENCE": {
    simpleExplanation:
      "When logging a statutory workplace accident, the official acknowledgement reference number from the authority must be recorded.",
    exampleScenario:
      "Maintaining accident logs and statutory incident records following a workplace injury.",
    compliantExample:
      "The incident register records the accident date alongside the official portal filing reference 'NOTICE-2026-0842'.",
    violationExample:
      "An accident is recorded internally but lacks the mandatory authority notification reference number.",
    actionToComply: [
      "Submit statutory accident notifications electronically to the Inspector within required deadlines.",
      "Record the official filing reference number in the statutory accident register.",
    ],
  },
  "OSH.HOURS.BEYOND_NORMAL_DAY_NOT_OVERTIME": {
    simpleExplanation:
      "When an employee works beyond 8 hours in a day, every excess hour must be recorded and paid as overtime at double the ordinary wage rate.",
    exampleScenario:
      "A factory operator works a 10 hour shift to finish an urgent production run.",
    compliantExample:
      "The attendance log records 8 normal hours and 2 overtime hours, and payroll compensates the 2 hours at double rate.",
    violationExample:
      "A worker is recorded working 12 hours on a shift, but overtime hours are recorded as 0 with no overtime pay.",
    actionToComply: [
      "Record every hour worked in excess of 8 hours per day as overtime in attendance records.",
      "Compensate overtime hours at not less than twice the regular hourly rate in payroll.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.REQUIRED_PARTICULARS": {
    simpleExplanation:
      "The appointment letter does not record every particular the appointment-letter rule requires, such as the employee's name, designation, joining date, wages, working hours or the employer's signature.",
    exampleScenario:
      "This check runs only when docs.appointment_letter_count > 0.",
    compliantExample:
      "Example (all particulars present): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_employee_name\": true, \"states_designation\": true, \"states_date_of_joining\": true, \"states_wage_rate\": true, \"states_working_hours\": true, \"is_signed_by_employer\": true}} — this passes.",
    violationExample:
      "Example (wage and hours absent): {\"docs\": {\"appointment_letter_count\": 1}, \"prose\": {\"states_employee_name\": true, \"states_designation\": true, \"states_date_of_joining\": true, \"states_wage_rate\": false, \"states_working_hours\": false, \"is_signed_by_employer\": true}} — this is reported.",
    actionToComply: [
      "Issue appointment letters that carry all prescribed particulars and retain a signed copy for every employee.",
      "Verify against OSH & Working Conditions Code, 2020 — s.6(1)(f); OSHWC (Central) Rules, 2026 — r.6.",
    ],
  },
};
