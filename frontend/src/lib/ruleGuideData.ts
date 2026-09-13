export interface RuleGuideItem {
  simpleExplanation: string;
  exampleScenario: string;
  compliantExample: string;
  violationExample: string;
  actionToComply: string[];
}

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
  "WAGES.DEFINITION.EXCLUDED_HALF": {
    simpleExplanation:
      "Specified excluded allowances (like HRA, conveyance, and travel perks) must not exceed 50% of total remuneration. If allowances exceed 50%, the excess is added back to 'Wages' for calculating PF, gratuity, and overtime.",
    exampleScenario:
      "An employee's monthly pay package is ₹40,000. Basic is ₹12,000 (30%) and various special allowances total ₹28,000 (70%).",
    compliantExample:
      "The maximum allowed excluded allowance is ₹20,000 (50%). The excess ₹8,000 is added to Basic, making the statutory wage base ₹20,000 for PF and gratuity.",
    violationExample:
      "Treating the ₹28,000 allowances as exempt and calculating PF on only ₹12,000, artificially deflating social security contributions.",
    actionToComply: [
      "Structure compensation packages so Basic + DA constitutes at least 50% of total pay.",
      "Audit salary structures across all pay bands to ensure compliance.",
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
  "WAGES.WAGE_SLIP.ISSUED": {
    simpleExplanation:
      "Employers must issue written or electronic wage slips (payslips) to every worker at least one day before wages are disbursed, showing earnings, hours worked, and deductions.",
    exampleScenario:
      "Monthly salary disbursement scheduled for the 7th of the month.",
    compliantExample:
      "Digital payslips or printed wage slips are handed over or emailed to all staff by the 6th of the month.",
    violationExample:
      "Paying salaries through bank transfer or cash without issuing any wage slips to workers.",
    actionToComply: [
      "Set up automatic email or SMS payslip distribution through your HRMS.",
      "Provide physical printed slips for workers without digital access.",
    ],
  },

  // =========================================================================
  // INDUSTRIAL RELATIONS CODE, 2020
  // =========================================================================
  "IR.WORKS_COMMITTEE.REQUIRED": {
    simpleExplanation:
      "Every industrial establishment with 100 or more workers must constitute a Works Committee with equal numbers of employer and worker representatives to promote cordial workplace relations.",
    exampleScenario:
      "A manufacturing facility operates with 140 permanent and shop-floor workers.",
    compliantExample:
      "The factory forms a 10-member Works Committee with 5 elected worker representatives and 5 management nominees that meets monthly.",
    violationExample:
      "Operating with 140 workers without ever setting up a Works Committee, depriving workers of a consultative forum.",
    actionToComply: [
      "Conduct elections among workers to choose their representatives.",
      "Pass a formal office memorandum constituting the Works Committee.",
      "Maintain minutes of all committee meetings.",
    ],
  },
  "IR.GRIEVANCE_COMMITTEE.REQUIRED": {
    simpleExplanation:
      "Every establishment employing 20 or more workers must set up a Grievance Redressal Committee to hear and resolve individual worker complaints fairly.",
    exampleScenario:
      "A technology startup or logistics hub expands its team to 28 employees.",
    compliantExample:
      "Management formalizes a 4-member Grievance Redressal Committee and publishes member details on the office notice board.",
    violationExample:
      "Operating with 28 workers with no formal grievance channel, forcing employees to take disputes outside the organization.",
    actionToComply: [
      "Form a committee with equal representation of management and workers.",
      "Display committee members' contact information prominently in the workplace.",
    ],
  },
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
  "IR.GRIEVANCE.DECISION_WITHIN_THIRTY_DAYS": {
    simpleExplanation:
      "The Grievance Redressal Committee must complete its investigation and deliver a formal written decision to the employee within 30 days of receiving their complaint.",
    exampleScenario:
      "A worker submits a written grievance regarding an unjustified fine on March 1st.",
    compliantExample:
      "The committee reviews evidence, conducts a hearing, and provides its written decision by March 24th (within 24 days).",
    violationExample:
      "The grievance sits pending with no action until June (90 days later), violating the statutory 30-day timeline.",
    actionToComply: [
      "Log all received grievances with date of receipt in a dedicated register.",
      "Set automated calendar reminders to ensure written closure within 30 days.",
    ],
  },
  "IR.STANDING_ORDERS.REQUIRED": {
    simpleExplanation:
      "Industrial establishments with 300 or more workers must prepare formal draft Standing Orders covering work rules, shifts, misconduct, and termination, and submit them for statutory certification.",
    exampleScenario:
      "An engineering plant scales up from 260 to 320 employees.",
    compliantExample:
      "The employer drafts Standing Orders based on Central Model Standing Orders and submits them to the Certifying Officer within 6 months.",
    violationExample:
      "Employing 350 workers while operating under informal guidelines without certified Standing Orders.",
    actionToComply: [
      "Prepare draft Standing Orders adhering to the Model Standing Orders.",
      "Consult worker representatives and file with the Certifying Officer.",
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
  "IR.RETRENCHMENT.PRIOR_PERMISSION": {
    simpleExplanation:
      "Industrial establishments (factories, mines, plantations) employing 300 or more workers must obtain prior approval from the government before laying off workers, retrenching staff, or closing down.",
    exampleScenario:
      "A manufacturing plant with 420 workers plans to lay off 40 workers due to falling orders.",
    compliantExample:
      "Management applies to the state labour commissioner 90 days in advance, providing detailed justification, and awaits official sanction.",
    violationExample:
      "The plant terminates 40 workers immediately without seeking prior government permission.",
    actionToComply: [
      "Submit statutory applications for lay-off/retrenchment at least 90 days in advance.",
      "Provide statutory severance pay (15 days' wages per completed year of service).",
    ],
  },

  // =========================================================================
  // OCCUPATIONAL SAFETY, HEALTH & WORKING CONDITIONS (OSH) CODE, 2020
  // =========================================================================
  "OSH.REGISTRATION.VALID": {
    simpleExplanation:
      "Every establishment employing 10 or more workers must register electronically with the labour department within 60 days of starting operations, and maintain a valid registration certificate.",
    exampleScenario:
      "A new business facility opens with 16 employees.",
    compliantExample:
      "The employer completes online registration on the Shram Suvidha portal within 60 days and downloads the electronic registration certificate.",
    violationExample:
      "Operating for 9 months with 16 workers without ever applying for establishment registration.",
    actionToComply: [
      "Register the establishment on the Shram Suvidha portal within 60 days of opening.",
      "Display the registration certificate on the office premises.",
    ],
  },
  "OSH.APPOINTMENT_LETTER.ISSUED": {
    simpleExplanation:
      "Employers must issue a formal written appointment letter to every single employee upon hiring, clearly specifying their designation, wages, duties, and work hours.",
    exampleScenario:
      "An organization hires 15 new operators and office helpers.",
    compliantExample:
      "Every newly hired worker receives a signed appointment letter on day one, and the employer retains their signed acknowledgment copy.",
    violationExample:
      "Hiring staff on oral agreements or informal WhatsApp messages without issuing an official appointment letter.",
    actionToComply: [
      "Issue standard appointment letters in English or regional language on day one.",
      "Maintain signed employee acceptance copies in personnel files.",
    ],
  },
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
  "OSH.ACCIDENT.NOTIFICATION_TIMELINESS": {
    simpleExplanation:
      "Fatal accidents must be reported within 12 hours. Non-fatal accidents causing 48+ hours of work absence must be notified within 48 hours of occurrence.",
    exampleScenario:
      "A severe machinery accident occurs on Monday at 10 AM, causing a worker severe fractures.",
    compliantExample:
      "Management submits the official accident notice to the authorities by Tuesday afternoon (well within 48 hours).",
    violationExample:
      "Reporting the incident 3 weeks later during a routine monthly administrative review.",
    actionToComply: [
      "Establish an emergency safety protocol to notify authorities within 12 to 48 hours.",
      "Transmit notices electronically via the state labour inspection portal.",
    ],
  },
  "OSH.HOURS.DAILY_CAP": {
    simpleExplanation:
      "No worker can be required or allowed to work more than 8 to 9 hours in any single day (excluding rest intervals). Working hours beyond this limit must be treated and paid as overtime.",
    exampleScenario:
      "A packaging unit runs extended day shifts to meet rush holiday orders.",
    compliantExample:
      "Workers complete an 8-hour shift plus a 1-hour lunch break; any additional 2 hours are logged and paid as double overtime.",
    violationExample:
      "Mandating 12 regular hours of work every day without shift rotation or statutory approvals.",
    actionToComply: [
      "Structure daily rosters around an 8-hour standard workday.",
      "Mandate rest intervals of at least 30 minutes after every 5 hours of continuous work.",
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
  "OSH.WELFARE.CRECHE": {
    simpleExplanation:
      "Every establishment employing 50 or more workers must provide a clean, safe creche (day-care) facility for children under 6 years of age, located on-site or within 500 metres.",
    exampleScenario:
      "A business or industrial plant employs 65 staff members.",
    compliantExample:
      "The company sets up an on-site creche with a qualified attendant or partners with an accredited day-care centre within 500m.",
    violationExample:
      "Employing 70 workers with no creche facility or day-care tie-up available.",
    actionToComply: [
      "Designate a well-ventilated, hygienic child-care room with suitable play materials.",
      "Allow female workers 4 visits daily to the creche including their rest intervals.",
    ],
  },
  "OSH.WELFARE.CANTEEN": {
    simpleExplanation:
      "Establishments employing 100 or more workers (in factories or notified classes) must provide an adequate, hygienic canteen facility serving nutritious food at reasonable rates.",
    exampleScenario:
      "A manufacturing facility operates with 130 shop-floor and office workers.",
    compliantExample:
      "Management provides a dedicated, hygienic dining area and kitchen serving hot meals at subsidised rates.",
    violationExample:
      "Operating with 150 workers without any canteen facility, forcing workers to eat on machinery floors or outside.",
    actionToComply: [
      "Set up a dedicated canteen with clean drinking water and sanitary dining tables.",
      "Engage an accredited food service vendor adhering to FSSAI standards.",
    ],
  },
  "OSH.HEALTH_CHECKUP.ANNUAL": {
    simpleExplanation:
      "Employers in hazardous processes or employing workers of prescribed ages (e.g. 45+ years) must arrange free annual medical health check-ups and maintain health records.",
    exampleScenario:
      "A chemical synthesis facility employs 40 operators handling corrosive liquids.",
    compliantExample:
      "A certified medical practitioner conducts comprehensive annual check-ups (audiometry, chest X-rays, blood panels) for all 40 workers free of cost.",
    violationExample:
      "Running hazardous chemical operations for three years without maintaining any annual employee health check-up records.",
    actionToComply: [
      "Tie up with an occupational health physician or certified hospital.",
      "Maintain health registers with Form-O check-up certificates for each worker.",
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
  "SS.ESIC.WORKERS_NOT_COVERED": {
    simpleExplanation:
      "Every employee earning up to ₹21,000 per month (₹25,000 for employees with disabilities) in an ESIC-covered establishment must be covered under ESIC medical and cash benefits.",
    exampleScenario:
      "A hospitality company employs 25 stewards earning ₹17,000 per month each.",
    compliantExample:
      "All 25 stewards are registered under ESIC, and monthly contributions (0.75% employee + 3.25% employer) are deposited.",
    violationExample:
      "Covering only 14 staff under ESIC and omitting the other 11 workers earning ₹17,000.",
    actionToComply: [
      "Review gross wages monthly and enroll anyone earning ₹21,000 or less into ESIC.",
      "File the monthly ESIC contribution return online before the due date.",
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
  "SS.EPF.DEPOSIT_TIMELINESS": {
    simpleExplanation:
      "EPF contributions (both employee and employer shares) must be deposited with the EPFO within 15 days of the close of each wage month (i.e. by the 15th of the following month).",
    exampleScenario:
      "EPF deductions made for the salary month of February.",
    compliantExample:
      "The electronic challan is generated and payment is settled on or before March 15th.",
    violationExample:
      "Depositing February contributions on March 29th, attracting penal damages and interest under Section 14B.",
    actionToComply: [
      "Generate monthly ECR challans by the 10th of each month.",
      "Complete bank payments well before the strict 15th-day statutory deadline.",
    ],
  },
  "SS.EPF.CONTRIBUTION_ARITHMETIC": {
    simpleExplanation:
      "The employee PF deduction from salary must mathematically equal 12% of the declared PF wage base. No random or mismatched deduction amounts are permitted.",
    exampleScenario:
      "An employee has a PF-qualifying wage base of ₹15,000.",
    compliantExample:
      "The deducted amount on the payslip and the ECR is exactly ₹1,800 (12% of ₹15,000).",
    violationExample:
      "Deducting ₹1,350 or ₹2,100 without a voluntary PF declaration, creating an audit error in the electronic challan.",
    actionToComply: [
      "Configure payroll deductions to strictly adhere to 12.00% of the qualifying wage.",
      "Run automated checks verifying that declared wage × 0.12 equals the deducted amount.",
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
  "SS.GRATUITY.FIXED_TERM_ELIGIBILITY": {
    simpleExplanation:
      "Fixed-term employees are entitled to gratuity on a pro-rata basis for the duration of their contract, without having to meet the 5-year continuous service rule required for regular workers.",
    exampleScenario:
      "An engineer is hired on a fixed-term contract of 18 months and completes the full term.",
    compliantExample:
      "Upon completion, the employer calculates and pays pro-rata gratuity for the 18 months of completed service.",
    violationExample:
      "Refusing gratuity to the fixed-term employee on the grounds that they did not complete 5 continuous years.",
    actionToComply: [
      "Set up pro-rata gratuity accruals for all fixed-term employment contracts.",
      "Disburse gratuity settlement upon contract completion along with final salary.",
    ],
  },
  "SS.AGGREGATOR.CONTRIBUTION": {
    simpleExplanation:
      "Digital platforms and aggregators (ride-hailing, food delivery, logistics) must contribute 1% to 2% of annual turnover (up to 5% of gig worker payouts) to the Social Security Fund.",
    exampleScenario:
      "An on-demand logistics delivery platform records ₹20 crore annual turnover and ₹4 crore payouts to delivery partners.",
    compliantExample:
      "The aggregator deposits 1% of turnover (₹20 lakh) into the Central Social Security Fund for gig worker welfare.",
    violationExample:
      "Operating a digital aggregator platform without registering with the Social Security Board or paying the welfare contribution.",
    actionToComply: [
      "Register the aggregator business on the national social security portal.",
      "Compute the statutory percentage of turnover and deposit to the designated fund.",
    ],
  },
};
