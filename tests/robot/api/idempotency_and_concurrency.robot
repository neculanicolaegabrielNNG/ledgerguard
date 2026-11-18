*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       api


*** Test Cases ***
Same Key And Payload Returns The Same Result Without Double Debit
    [Tags]    idempotency
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${key}=    New Key
    ${first}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    30000    key=${key}
    ${second}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    30000    key=${key}
    Status Should Be    ${first}    201
    Status Should Be    ${second}    201
    Should Be Equal    ${first}[body][id]    ${second}[body][id]
    Should Be Equal    ${second}[headers][idempotent-replay]    true
    Should Not Contain    ${first}[headers]    idempotent-replay
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    70000
    ${count}=    Scalar    SELECT COUNT(*) FROM transfers
    Should Be Equal As Integers    ${count}    1
    ${transactions}=    Scalar    SELECT COUNT(*) FROM transactions WHERE kind = 'transfer'
    Should Be Equal As Integers    ${transactions}    1

# ————————————————————————————————————————

Same Key With Different Payload Is Rejected
    [Tags]    idempotency
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${key}=    New Key
    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    1000    key=${key}
    ${second}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    2000    key=${key}
    Status Should Be    ${second}    409
    Error Code Should Be    ${second}    idempotency_key_reuse
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    99000

# ————————————————————————————————————————

Failed Request Does Not Consume The Key
    [Tags]    idempotency
    ${sender}    ${receiver}=    Customer Pair    RON    1000
    ${key}=    New Key
    ${failed}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    5000    key=${key}
    Status Should Be    ${failed}    422
    Deposit    ${sender}[account_id]    10000
    ${retry}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    5000    key=${key}
    Status Should Be    ${retry}    201

# ————————————————————————————————————————

Deposit Is Idempotent
    [Tags]    idempotency
    ${client}=    Create Funded Customer    RON    0
    ${key}=    New Key
    &{headers}=    Create Dictionary    Idempotency-Key=${key}
    &{body}=    Create Dictionary    amount_minor=${7000}
    ${first}=    Admin Request    POST    /accounts/${client}[account_id]/deposit    json=${body}    headers=${headers}
    ${second}=    Admin Request    POST    /accounts/${client}[account_id]/deposit    json=${body}    headers=${headers}
    Status Should Be    ${first}    201
    Status Should Be    ${second}    201
    ${balance}=    Account Balance    ${client}[token]    ${client}[account_id]
    Should Be Equal As Integers    ${balance}    7000

# ————————————————————————————————————————

Concurrent Duplicate Requests Execute Exactly Once
    [Tags]    idempotency    concurrency
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${key}=    New Key
    &{headers}=    Create Dictionary    Idempotency-Key=${key}
    &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${20000}
    &{request}=    Create Dictionary    method=POST    path=/transfers    token=${sender}[token]    json=${body}    headers=${headers}
    ${requests}=    Evaluate    [dict($request) for _ in range(5)]
    ${results}=    Concurrent Requests    ${requests}
    FOR    ${result}    IN    @{results}
        Status Should Be    ${result}    201
    END
    ${ids}=    Evaluate    {item["body"]["id"] for item in $results}
    Length Should Be    ${ids}    1
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    80000

# ————————————————————————————————————————

Two Concurrent Transfers Cannot Overdraw An Account
    [Tags]    concurrency
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${requests}=    Create List
    FOR    ${index}    IN RANGE    2
        &{headers}=    Create Dictionary    Idempotency-Key=${{ "concurrent-" + str($index) + "-" + $sender["account_id"] }}
        &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${70000}
        &{request}=    Create Dictionary    method=POST    path=/transfers    token=${sender}[token]    json=${body}    headers=${headers}
        Append To List    ${requests}    ${request}
    END
    ${results}=    Concurrent Requests    ${requests}
    ${statuses}=    Evaluate    sorted(item["status"] for item in $results)
    Should Be Equal    ${statuses}    ${{ [201, 422] }}
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    30000
    ${negative}=    Customer Negative Balances
    Should Be Empty    ${negative}
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Many Concurrent Transfers Preserve Total Money And Never Go Negative
    [Tags]    concurrency
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${total_before}=    Total Money    RON
    ${requests}=    Create List
    FOR    ${index}    IN RANGE    8
        &{headers}=    Create Dictionary    Idempotency-Key=${{ "many-" + str($index) + "-" + $sender["account_id"] }}
        &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${20000}
        &{request}=    Create Dictionary    method=POST    path=/transfers    token=${sender}[token]    json=${body}    headers=${headers}
        Append To List    ${requests}    ${request}
    END
    ${results}=    Concurrent Requests    ${requests}
    ${completed}=    Evaluate    len([item for item in $results if item["status"] == 201])
    ${rejected}=    Evaluate    len([item for item in $results if item["status"] == 422])
    Should Be Equal As Integers    ${completed}    5
    Should Be Equal As Integers    ${rejected}    3
    ${sender_balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${sender_balance}    0
    ${total_after}=    Total Money    RON
    Should Be Equal As Integers    ${total_after}    ${total_before}
    Ledger Invariants Should Hold
