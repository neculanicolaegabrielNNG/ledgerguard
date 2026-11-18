*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       fraud


*** Keywords ***
Small Transfers
    [Arguments]    ${sender}    ${receiver}    ${count}    ${amount}=10000    ${pause}=3600
    FOR    ${index}    IN RANGE    ${count}
        Send Transfer    ${sender}    ${receiver}    ${amount}
        Advance Clock    ${pause}
    END

# ————————————————————————————————————————

Aged Pair
    [Arguments]    ${balance}=20000000
    ${sender}    ${receiver}=    Customer Pair    RON    ${balance}
    Age Accounts
    RETURN    ${sender}    ${receiver}


*** Test Cases ***
Amount Far Above Customer History Is Flagged
    [Tags]    rule:amount_vs_history
    ${sender}    ${receiver}=    Aged Pair
    Small Transfers    ${sender}    ${receiver}    3
    ${large}=    Send Transfer    ${sender}    ${receiver}    400000
    ${types}=    Triggered Types    ${large}[body][id]
    Should Contain    ${types}    amount_vs_history
    ${small}=    Send Transfer    ${sender}    ${receiver}    20000
    ${types}=    Triggered Types    ${small}[body][id]
    Should Not Contain    ${types}    amount_vs_history

# ————————————————————————————————————————

Many Transfers In A Short Interval Are Flagged
    [Tags]    rule:velocity
    ${sender}    ${receiver}=    Aged Pair
    Small Transfers    ${sender}    ${receiver}    5    1000    10
    ${sixth}=    Send Transfer    ${sender}    ${receiver}    1000
    ${types}=    Triggered Types    ${sixth}[body][id]
    Should Contain    ${types}    velocity
    Advance Clock    7200
    ${later}=    Send Transfer    ${sender}    ${receiver}    1000
    ${types}=    Triggered Types    ${later}[body][id]
    Should Not Contain    ${types}    velocity

# ————————————————————————————————————————

Fragmented Transfers Below The Threshold Are Flagged
    [Tags]    rule:structuring
    ${sender}    ${receiver}=    Aged Pair
    Send Transfer    ${sender}    ${receiver}    4500000
    Advance Clock    600
    Send Transfer    ${sender}    ${receiver}    4600000
    Advance Clock    600
    ${third}=    Send Transfer    ${sender}    ${receiver}    4700000
    ${types}=    Triggered Types    ${third}[body][id]
    Should Contain    ${types}    structuring
    Should Not Be Equal    ${third}[body][state]    completed

# ————————————————————————————————————————

New Account With High Volume Is Flagged
    [Tags]    rule:new_account_volume
    ${sender}    ${receiver}=    Customer Pair    RON    20000000
    ${response}=    Send Transfer    ${sender}    ${receiver}    2500000
    ${types}=    Triggered Types    ${response}[body][id]
    Should Contain    ${types}    new_account_volume
    Should Be Equal    ${response}[body][state]    under_review

# ————————————————————————————————————————

Aged Account Is Not Flagged For The Same Volume
    [Tags]    rule:new_account_volume
    ${sender}    ${receiver}=    Aged Pair
    ${response}=    Send Transfer    ${sender}    ${receiver}    2500000
    ${types}=    Triggered Types    ${response}[body][id]
    Should Not Contain    ${types}    new_account_volume

# ————————————————————————————————————————

Large Transfer To A New Beneficiary Is Flagged Once
    [Tags]    rule:new_beneficiary_large
    ${sender}    ${receiver}=    Aged Pair
    ${first}=    Send Transfer    ${sender}    ${receiver}    2000000
    ${types}=    Triggered Types    ${first}[body][id]
    Should Contain    ${types}    new_beneficiary_large
    Should Be Equal    ${first}[body][state]    completed
    ${second}=    Send Transfer    ${sender}    ${receiver}    2000000
    ${types}=    Triggered Types    ${second}[body][id]
    Should Not Contain    ${types}    new_beneficiary_large

# ————————————————————————————————————————

Circle Of Transfers Between Linked Accounts Is Flagged
    [Tags]    rule:circular_flow
    ${first}=    Create Funded Customer    RON    5000000
    ${second}=    Create Funded Customer    RON    5000000
    ${third}=    Create Funded Customer    RON    5000000
    Age Accounts
    Send Transfer    ${first}    ${second}    100000
    Advance Clock    600
    Send Transfer    ${second}    ${third}    90000
    Advance Clock    600
    ${closing}=    Send Transfer    ${third}    ${first}    80000
    ${types}=    Triggered Types    ${closing}[body][id]
    Should Contain    ${types}    circular_flow
    Should Be Equal    ${closing}[body][state]    under_review

# ————————————————————————————————————————

Sudden Change In Behavior Is Flagged
    [Tags]    rule:behavior_change
    ${sender}    ${receiver}=    Aged Pair
    Small Transfers    ${sender}    ${receiver}    6    20000    3600
    Advance Clock    ${{ 3 * 86400 }}
    ${spike}=    Send Transfer    ${sender}    ${receiver}    900000
    ${types}=    Triggered Types    ${spike}[body][id]
    Should Contain    ${types}    behavior_change

# ————————————————————————————————————————

Abnormal Exchange Rate At Transaction Time Is Flagged
    [Tags]    rule:fx_anomaly
    ${sender}    ${receiver}=    Customer Pair    EUR    5000000    EUR
    Age Accounts
    Shock Fx    EUR    500
    Refresh Fx
    ${response}=    Send Transfer    ${sender}    ${receiver}    10000
    ${types}=    Triggered Types    ${response}[body][id]
    Should Contain    ${types}    fx_anomaly

# ————————————————————————————————————————

Recent Rate Alert Also Flags Foreign Currency Transfers
    [Tags]    rule:fx_anomaly
    ${sender}    ${receiver}=    Customer Pair    USD    5000000    USD
    Shock Fx    USD    5000
    Refresh Fx
    ${response}=    Send Transfer    ${sender}    ${receiver}    10000
    ${types}=    Triggered Types    ${response}[body][id]
    Should Contain    ${types}    fx_anomaly

# ————————————————————————————————————————

Evaluation Lists Every Rule With Measured Values And Versions
    ${sender}    ${receiver}=    Aged Pair
    ${response}=    Send Transfer    ${sender}    ${receiver}    1000
    ${detail}=    Admin Request    GET    /transfers/${response}[body][id]
    ${results}=    Set Variable    ${detail}[body][evaluation][results]
    Length Should Be    ${results}    8
    FOR    ${item}    IN    @{results}
        Dictionary Should Contain Key    ${item}    measured
        Dictionary Should Contain Key    ${item}    threshold
        Should Be Equal As Integers    ${item}[rule_version]    1
    END
    ${score}=    Set Variable    ${detail}[body][evaluation][score]
    Should Be Equal As Integers    ${score}    ${detail}[body][risk_score]

# ————————————————————————————————————————

Rule Update Creates A New Version And Keeps History
    ${before}=    Admin Request    GET    /fraud/rules    params=${{ {"rule_id": "R-VELOCITY", "include_history": True} }}
    Length Should Be    ${before}[body][items]    1
    ${changes}=    Evaluate    {"params": {"max_count": 2}}
    ${updated}=    Update Rule    R-VELOCITY    ${changes}
    Should Be Equal As Integers    ${updated}[body][version]    2
    ${history}=    Admin Request    GET    /fraud/rules    params=${{ {"rule_id": "R-VELOCITY", "include_history": True} }}
    ${versions}=    Evaluate    [item["version"] for item in $history["body"]["items"]]
    Should Be Equal    ${versions}    ${{ [1, 2] }}
    ${old}=    Set Variable    ${history}[body][items][0][params][max_count]
    ${new}=    Set Variable    ${history}[body][items][1][params][max_count]
    Should Be Equal As Integers    ${old}    5
    Should Be Equal As Integers    ${new}    2
    ${audited}=    Scalar    SELECT COUNT(*) FROM audit_log WHERE action = 'fraud.rule_updated' AND entity_id = 'R-VELOCITY'
    Should Be Equal As Integers    ${audited}    1
    ${rows}=    Scalar    SELECT COUNT(*) FROM fraud_rules WHERE id = 'R-VELOCITY'
    Should Be Equal As Integers    ${rows}    2

# ————————————————————————————————————————

New Rule Version Applies To Later Evaluations Only
    ${sender}    ${receiver}=    Aged Pair
    ${first}=    Send Transfer    ${sender}    ${receiver}    1000
    ${changes}=    Evaluate    {"params": {"max_count": 0}}
    Update Rule    R-VELOCITY    ${changes}
    ${second}=    Send Transfer    ${sender}    ${receiver}    1000
    ${first_types}=    Triggered Types    ${first}[body][id]
    ${second_types}=    Triggered Types    ${second}[body][id]
    Should Not Contain    ${first_types}    velocity
    Should Contain    ${second_types}    velocity
    ${detail}=    Admin Request    GET    /transfers/${second}[body][id]
    ${velocity}=    Evaluate    [item for item in $detail["body"]["evaluation"]["results"] if item["rule_id"] == "R-VELOCITY"][0]
    Should Be Equal As Integers    ${velocity}[rule_version]    2

# ————————————————————————————————————————

Inactive Rule Is Not Applied
    ${sender}    ${receiver}=    Aged Pair
    Disable Rule    R-VELOCITY
    Small Transfers    ${sender}    ${receiver}    7    1000    10
    ${last}=    Send Transfer    ${sender}    ${receiver}    1000
    ${detail}=    Admin Request    GET    /transfers/${last}[body][id]
    ${ids}=    Evaluate    [item["rule_id"] for item in $detail["body"]["evaluation"]["results"]]
    Should Not Contain    ${ids}    R-VELOCITY
    Length Should Be    ${ids}    7

# ————————————————————————————————————————

Block Effect Blocks The Transfer And Emits An Event
    Admin Request    POST    /webhooks    json=${{ {"url": "https://example.test/hook", "events": ["transfer.blocked"]} }}
    ${changes}=    Evaluate    {"effect": "block", "params": {"amount_ron_minor": 1000}}
    Update Rule    R-NEW-BENEFICIARY    ${changes}
    ${sender}    ${receiver}=    Aged Pair
    ${response}=    Send Transfer    ${sender}    ${receiver}    5000
    Should Be Equal    ${response}[body][state]    blocked
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    20000000
    ${events}=    Query    SELECT event FROM webhook_deliveries
    Length Should Be    ${events}    1

# ————————————————————————————————————————

Combined Score At The Block Threshold Blocks Without A Block Effect
    ${sender}    ${receiver}=    Customer Pair    RON    20000000
    ${third}=    Create Funded Customer    RON    0
    Small Transfers    ${sender}    ${receiver}    3
    ${response}=    Send Transfer    ${sender}    ${third}    2500000
    ${types}=    Triggered Types    ${response}[body][id]
    Should Contain    ${types}    amount_vs_history
    Should Contain    ${types}    new_account_volume
    Should Contain    ${types}    new_beneficiary_large
    Should Be Equal    ${response}[body][state]    blocked
    ${detail}=    Admin Request    GET    /transfers/${response}[body][id]
    Should Be Equal As Integers    ${detail}[body][evaluation][score]    100
    Should Be Equal    ${detail}[body][evaluation][decision]    block

# ————————————————————————————————————————

Rule Parameters Are Validated
    ${negative}=    Evaluate    {"params": {"max_count": -1}}
    ${response}=    Admin Request    PUT    /fraud/rules/R-VELOCITY    json=${negative}
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    invalid_rule_params
    ${unknown}=    Admin Request    PUT    /fraud/rules/R-DOES-NOT-EXIST    json=${{ {"active": False} }}
    Status Should Be    ${unknown}    404
    ${empty}=    Admin Request    PUT    /fraud/rules/R-VELOCITY    json=${{ {} }}
    Status Should Be    ${empty}    422
    ${bad_effect}=    Admin Request    PUT    /fraud/rules/R-VELOCITY    json=${{ {"effect": "explode"} }}
    Status Should Be    ${bad_effect}    422

# ————————————————————————————————————————

Only Admin Can Change Rules
    ${response}=    Compliance Request    PUT    /fraud/rules/R-VELOCITY    json=${{ {"active": False} }}
    Status Should Be    ${response}    403
    ${read}=    Compliance Request    GET    /fraud/rules
    Status Should Be    ${read}    200
    Length Should Be    ${read}[body][items]    8

# ————————————————————————————————————————

Review Queue Is Sorted By Risk
    ${low}=    Evaluate    {"effect": "review", "params": {"amount_ron_minor": 1000, "score": 55}}
    Update Rule    R-NEW-BENEFICIARY    ${low}
    ${sender}    ${receiver}=    Aged Pair
    ${first}=    Send Transfer    ${sender}    ${receiver}    5000
    ${third}=    Create Funded Customer    RON    0
    ${high}=    Evaluate    {"params": {"score": 80}}
    Update Rule    R-NEW-BENEFICIARY    ${high}
    ${second}=    Send Transfer    ${sender}    ${third}    5000
    ${queue}=    Compliance Request    GET    /fraud/cases
    Status Should Be    ${queue}    200
    ${scores}=    Evaluate    [item["score"] for item in $queue["body"]["items"]]
    Should Be Equal    ${scores}    ${{ [80, 55] }}

# ————————————————————————————————————————

Time Travel Shows Balances Rules And Decisions At A Past Moment
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${moment}=    Clock Now
    Advance Clock    120
    ${changes}=    Evaluate    {"params": {"max_count": 1}}
    Update Rule    R-VELOCITY    ${changes}
    Send Transfer    ${sender}    ${receiver}    40000
    ${past}=    Compliance Request    GET    /timetravel    params=${{ {"at": $moment} }}
    Status Should Be    ${past}    200
    ${balance}=    Evaluate    [item["balance_minor"] for item in $past["body"]["balances"] if item["account_id"] == $sender["account_id"]][0]
    Should Be Equal As Integers    ${balance}    100000
    ${velocity}=    Evaluate    [item for item in $past["body"]["rules"] if item["id"] == "R-VELOCITY"][0]
    Should Be Equal As Integers    ${velocity}[version]    1
    Should Be Equal As Integers    ${velocity}[params][max_count]    5
    Should Be Empty    ${past}[body][decisions]
    ${current}=    Compliance Request    GET    /timetravel    params=${{ {"at": "2999-01-01T00:00:00Z"} }}
    Status Should Be    ${current}    200
    Length Should Be    ${current}[body][decisions]    1
    ${later_velocity}=    Evaluate    [item for item in $current["body"]["rules"] if item["id"] == "R-VELOCITY"][0]
    Should Be Equal As Integers    ${later_velocity}[version]    2

# ————————————————————————————————————————

Network Graph Highlights Suspicious Clusters
    ${first}=    Create Funded Customer    RON    5000000
    ${second}=    Create Funded Customer    RON    5000000
    ${third}=    Create Funded Customer    RON    5000000
    Age Accounts
    Send Transfer    ${first}    ${second}    100000
    Advance Clock    600
    Send Transfer    ${second}    ${third}    90000
    Advance Clock    600
    Send Transfer    ${third}    ${first}    80000
    ${graph}=    Compliance Request    GET    /fraud/graph
    Status Should Be    ${graph}    200
    Length Should Be    ${graph}[body][nodes]    3
    Length Should Be    ${graph}[body][clusters]    1
    ${suspicious}=    Evaluate    [item for item in $graph["body"]["nodes"] if item["suspicious"]]
    Length Should Be    ${suspicious}    3
