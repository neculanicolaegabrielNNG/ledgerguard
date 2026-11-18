*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       agents


*** Keywords ***
Run Simulation
    [Arguments]    ${strategy}    ${seed}=1    ${benign}=8
    &{body}=    Create Dictionary    strategy=${strategy}    seed=${seed}    benign_count=${benign}
    ${response}=    Admin Request    POST    /simulation/runs    json=${body}
    Status Should Be    ${response}    201
    RETURN    ${response}[body]


*** Test Cases ***
Same Seed Produces Identical Metrics
    [Tags]    simulation
    ${first}=    Run Simulation    structuring    5    6
    ${second}=    Run Simulation    structuring    5    6
    Should Be Equal    ${first}[metrics]    ${second}[metrics]
    ${first_outcomes}=    Evaluate    [(item["label"], item["state"], item["offset_seconds"]) for item in $first["steps"]]
    ${second_outcomes}=    Evaluate    [(item["label"], item["state"], item["offset_seconds"]) for item in $second["steps"]]
    Should Be Equal    ${first_outcomes}    ${second_outcomes}

# ————————————————————————————————————————

Same Seed Is Reproducible Across Fresh Systems
    [Tags]    simulation
    ${first}=    Run Simulation    account_takeover    9    5
    Stop Fresh System
    Start Fresh System
    ${second}=    Run Simulation    account_takeover    9    5
    Should Be Equal    ${first}[metrics]    ${second}[metrics]

# ————————————————————————————————————————

Every Attack Strategy Is Detected At Least Once
    [Tags]    simulation
    FOR    ${strategy}    IN    structuring    mule_accounts    account_takeover    transfer_cycle
        ${run}=    Run Simulation    ${strategy}    3    6
        Should Be True    ${run}[metrics][malicious_caught] >= 1    msg=${strategy} nu a fost detectată
        Should Be True    ${run}[metrics][steps_to_detection] >= 1
        Should Be Equal As Integers    ${run}[metrics][errors]    0    msg=${strategy}: pași eșuați
    END

# ————————————————————————————————————————

Legitimate Traffic Raises No False Alarms
    [Tags]    simulation
    ${run}=    Run Simulation    transfer_cycle    4    20
    Should Be Equal As Integers    ${run}[metrics][false_alarms]    0
    Should Be True    ${run}[metrics][benign_total] == 20

# ————————————————————————————————————————

Simulation Metrics Report Detection Quality
    [Tags]    simulation
    ${run}=    Run Simulation    structuring    1    4
    ${metrics}=    Set Variable    ${run}[metrics]
    FOR    ${field}    IN    malicious_total    malicious_caught    malicious_missed    benign_total    false_alarms    detection_rate_pct    false_alarm_rate_pct    steps_to_detection    seconds_to_detection
        Dictionary Should Contain Key    ${metrics}    ${field}
    END
    ${total}=    Evaluate    $metrics["malicious_caught"] + $metrics["malicious_missed"]
    Should Be Equal As Integers    ${total}    ${metrics}[malicious_total]

# ————————————————————————————————————————

Simulation Results Are Stored And Listed
    [Tags]    simulation
    ${run}=    Run Simulation    transfer_cycle    2    4
    ${listed}=    Compliance Request    GET    /simulation/runs
    Status Should Be    ${listed}    200
    ${ids}=    Evaluate    [item["id"] for item in $listed["body"]["items"]]
    Should Contain    ${ids}    ${run}[id]
    ${stored}=    Compliance Request    GET    /simulation/runs/${run}[id]
    Status Should Be    ${stored}    200
    Should Be Equal    ${stored}[body][metrics]    ${run}[metrics]
    ${rows}=    Scalar    SELECT COUNT(*) FROM simulation_runs
    Should Be Equal As Integers    ${rows}    1

# ————————————————————————————————————————

Simulation Runs Through The Real Api And Leaves Ledger Consistent
    [Tags]    simulation
    Run Simulation    structuring    1    8
    Run Simulation    mule_accounts    1    8
    Ledger Invariants Should Hold
    ${audited}=    Scalar    SELECT COUNT(*) FROM audit_log WHERE action = 'transfer.created'
    Should Be True    ${audited} > 10

# ————————————————————————————————————————

Only Admin Can Start A Simulation
    [Tags]    simulation    roles
    &{body}=    Create Dictionary    strategy=structuring    seed=${1}    benign_count=${2}
    ${response}=    Compliance Request    POST    /simulation/runs    json=${body}
    Status Should Be    ${response}    403
    ${unknown}=    Admin Request    POST    /simulation/runs    json=${{ {"strategy": "nonsense"} }}
    Status Should Be    ${unknown}    422
    Error Code Should Be    ${unknown}    unknown_strategy

# ————————————————————————————————————————

Synthetic Data Generation Is Reproducible For A Seed
    [Tags]    testing_agent
    &{body}=    Create Dictionary    seed=${3}    customers=${4}    transfers_per_customer=${3}
    ${first}=    Admin Request    POST    /quality/synthetic    json=${body}
    Status Should Be    ${first}    201
    Stop Fresh System
    Start Fresh System
    ${second}=    Admin Request    POST    /quality/synthetic    json=${body}
    Status Should Be    ${second}    201
    Should Be Equal    ${first}[body][transfers_attempted]    ${second}[body][transfers_attempted]
    Should Be Equal    ${first}[body][transfers_completed]    ${second}[body][transfers_completed]
    Should Be Equal    ${first}[body][transfers_flagged]    ${second}[body][transfers_flagged]
    Length Should Be    ${first}[body][customers]    4
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Synthetic Customers Can Log In
    [Tags]    testing_agent
    &{body}=    Create Dictionary    seed=${1}    customers=${2}    transfers_per_customer=${1}    password=synthetic-pass-123
    ${created}=    Admin Request    POST    /quality/synthetic    json=${body}
    Status Should Be    ${created}    201
    &{login}=    Create Dictionary    email=${created}[body][customers][0]    password=synthetic-pass-123
    ${response}=    Api Request    POST    /auth/login    json=${login}
    Status Should Be    ${response}    200

# ————————————————————————————————————————

Api Test Cases Are Proposed From The OpenAPI Schema
    [Tags]    testing_agent
    ${first}=    Admin Request    POST    /quality/proposals    json=${{ {"seed": 1, "count": 4} }}
    Status Should Be    ${first}    201
    Should Be True    ${first}[body][api_cases_created] > 20
    Should Be Equal As Integers    ${first}[body][scenarios_created]    4
    ${listed}=    Admin Request    GET    /quality/proposals    params=${{ {"kind": "api_case", "limit": 200} }}
    ${titles}=    Evaluate    [item["title"] for item in $listed["body"]["items"]]
    ${expected}=    Evaluate    "POST /api/v1/transfers: 400 fără Idempotency-Key"
    Should Contain    ${titles}    ${expected}
    ${second}=    Admin Request    POST    /quality/proposals    json=${{ {"seed": 1, "count": 4} }}
    Should Be Equal As Integers    ${second}[body][api_cases_created]    0
    Should Be Equal As Integers    ${second}[body][scenarios_created]    0

# ————————————————————————————————————————

Failure Triage Marks Infrastructure Errors As Flaky
    [Tags]    testing_agent
    Write Robot Output    run-1    Api|Locking Test|FAIL|database is locked|    Api|Balance Test|FAIL|1 != 2|
    ${response}=    Admin Request    POST    /quality/triage
    Status Should Be    ${response}    200
    ${verdicts}=    Evaluate    {item["test"]: item for item in $response["body"]["verdicts"]}
    Should Be Equal    ${verdicts}[Locking Test][verdict]    flaky
    Should Be Equal    ${verdicts}[Balance Test][verdict]    real_bug
    Should Not Be Empty    ${verdicts}[Balance Test][reason]

# ————————————————————————————————————————

Failure Triage Uses History To Spot Regressions
    [Tags]    testing_agent
    Write Robot Output    run-a    Api|Stable Test|PASS||
    Admin Request    POST    /quality/triage
    Write Robot Output    run-b    Api|Stable Test|PASS||
    Admin Request    POST    /quality/triage
    Write Robot Output    run-c    Api|Stable Test|FAIL|3 != 4|
    ${response}=    Admin Request    POST    /quality/triage
    ${verdict}=    Set Variable    ${response}[body][verdicts][0]
    Should Be Equal    ${verdict}[verdict]    real_bug
    Should Be Equal    ${verdict}[confidence]    high

# ————————————————————————————————————————

Failure Triage Marks Mixed History As Flaky
    [Tags]    testing_agent
    Write Robot Output    run-a    Api|Wobbly Test|PASS||
    Admin Request    POST    /quality/triage
    Write Robot Output    run-b    Api|Wobbly Test|FAIL|3 != 4|
    Admin Request    POST    /quality/triage
    Write Robot Output    run-c    Api|Wobbly Test|FAIL|3 != 4|
    ${response}=    Admin Request    POST    /quality/triage
    Should Be Equal    ${response}[body][verdicts][0][verdict]    flaky

# ————————————————————————————————————————

Quality Panel Reports Rule Coverage From Tagged Tests
    [Tags]    testing_agent
    Write Robot Output    run-1    Fraud|Velocity Test|PASS||rule:velocity    Fraud|Circular Test|PASS||rule:circular_flow    Fraud|Broken Test|FAIL|x != y|rule:structuring
    ${panel}=    Compliance Request    GET    /quality/panel
    Status Should Be    ${panel}    200
    Should Be Equal As Integers    ${panel}[body][tests][total]    3
    Should Be Equal As Integers    ${panel}[body][tests][passed]    2
    Should Be Equal As Integers    ${panel}[body][tests][failed]    1
    Should Be Equal As Integers    ${panel}[body][rules_total]    8
    Should Be Equal As Integers    ${panel}[body][rules_covered]    2

# ————————————————————————————————————————

Quality Panel Works Without Test Results
    [Tags]    testing_agent
    ${panel}=    Compliance Request    GET    /quality/panel
    Status Should Be    ${panel}    200
    Should Be Equal    ${panel}[body][tests][available]    ${False}
