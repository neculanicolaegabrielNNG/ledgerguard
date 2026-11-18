*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       api


*** Test Cases ***
Same Currency Transfer Moves Money And Completes
    [Tags]    transfers
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    25000    chirie
    Transfer State Should Be    ${response}    completed
    ${sender_balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    ${receiver_balance}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${sender_balance}    75000
    Should Be Equal As Integers    ${receiver_balance}    25000
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Insufficient Funds Are Rejected Without Side Effects
    [Tags]    transfers
    ${sender}    ${receiver}=    Customer Pair    RON    10000
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    10001
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    insufficient_funds
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    10000
    ${count}=    Scalar    SELECT COUNT(*) FROM transfers
    Should Be Equal As Integers    ${count}    0

# ————————————————————————————————————————

Transfer To The Same Account Is Rejected
    [Tags]    transfers
    ${sender}    ${receiver}=    Customer Pair
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${sender}[account_id]    1000
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    same_account

# ————————————————————————————————————————

Customer Cannot Spend From Another Customers Account
    [Tags]    transfers    roles
    ${first}    ${second}=    Customer Pair
    ${response}=    Make Transfer    ${second}[token]    ${first}[account_id]    ${second}[account_id]    1000
    Status Should Be    ${response}    403
    Error Code Should Be    ${response}    forbidden

# ————————————————————————————————————————

Transfers Cannot Target System Accounts
    [Tags]    transfers
    ${sender}    ${receiver}=    Customer Pair
    ${system}=    Query    SELECT id FROM accounts WHERE system_key = 'CASH-RON'
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${system}[0][id]    1000
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    account_not_transferable

# ————————————————————————————————————————

Non Positive Amounts Are Rejected
    [Tags]    transfers
    ${sender}    ${receiver}=    Customer Pair
    ${zero}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    0
    Status Should Be    ${zero}    422
    ${negative}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    -5
    Status Should Be    ${negative}    422

# ————————————————————————————————————————

Transfer History Filters By State And Account
    [Tags]    transfers    pagination
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    Send Transfer    ${sender}    ${receiver}    1000
    Send Transfer    ${sender}    ${receiver}    2000
    ${completed}=    Api Request    GET    /transfers    ${sender}[token]    params=${{ {"state": "completed"} }}
    Length Should Be    ${completed}[body][items]    2
    ${blocked}=    Api Request    GET    /transfers    ${sender}[token]    params=${{ {"state": "blocked"} }}
    Length Should Be    ${blocked}[body][items]    0
    ${by_account}=    Api Request    GET    /transfers    ${receiver}[token]    params=${{ {"account_id": $receiver["account_id"]} }}
    Length Should Be    ${by_account}[body][items]    0

# ————————————————————————————————————————

Customers See Only Their Own Transfers And No Risk Data
    [Tags]    transfers    roles
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${created}=    Send Transfer    ${sender}    ${receiver}    1000
    ${other}=    Api Request    GET    /transfers/${created}[body][id]    ${receiver}[token]
    Status Should Be    ${other}    403
    ${own}=    Api Request    GET    /transfers/${created}[body][id]    ${sender}[token]
    Status Should Be    ${own}    200
    Should Be Equal    ${own}[body][evaluation]    ${None}
    ${internal}=    Admin Request    GET    /transfers/${created}[body][id]
    Should Not Be Empty    ${internal}[body][evaluation][results]

# ————————————————————————————————————————

Quote Matches The Executed Conversion
    [Tags]    transfers    fx
    ${sender}    ${receiver}=    Customer Pair    EUR    100000    USD
    ${quote}=    Api Request    GET    /transfers/quote    ${sender}[token]    params=${{ {"from_account_id": $sender["account_id"], "to_account_id": $receiver["account_id"], "amount_minor": 50000} }}
    Status Should Be    ${quote}    200
    ${response}=    Send Transfer    ${sender}    ${receiver}    50000
    Should Be Equal As Integers    ${response}[body][target_amount_minor]    ${quote}[body][target_amount_minor]
    ${received}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${received}    ${quote}[body][target_amount_minor]

# ————————————————————————————————————————

Scheduled Payment Runs When Due And Only Once Per Interval
    [Tags]    transfers    scheduled
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    &{schedule}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${5000}    interval_seconds=${3600}
    ${created}=    Api Request    POST    /scheduled-payments    ${sender}[token]    json=${schedule}
    Status Should Be    ${created}    201
    Run Maintenance
    ${before}=    Scalar    SELECT COUNT(*) FROM transfers
    Should Be Equal As Integers    ${before}    0
    Advance Clock    3601
    Run Maintenance
    Run Maintenance
    ${after}=    Scalar    SELECT COUNT(*) FROM transfers WHERE channel = 'scheduled'
    Should Be Equal As Integers    ${after}    1
    ${balance}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${balance}    5000

# ————————————————————————————————————————

Scheduled Payment Can Be Cancelled
    [Tags]    transfers    scheduled
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    &{schedule}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${5000}    interval_seconds=${3600}
    ${created}=    Api Request    POST    /scheduled-payments    ${sender}[token]    json=${schedule}
    ${removed}=    Api Request    DELETE    /scheduled-payments/${created}[body][id]    ${sender}[token]
    Status Should Be    ${removed}    204
    Advance Clock    7200
    Run Maintenance
    ${count}=    Scalar    SELECT COUNT(*) FROM transfers
    Should Be Equal As Integers    ${count}    0

# ————————————————————————————————————————

Generated OpenAPI Matches The Documented Contract
    [Tags]    contract
    ${problems}=    Contract Violations
    Should Be Empty    ${problems}

# ————————————————————————————————————————

Money Moving Routes Require An Idempotency Key
    [Tags]    contract    idempotency
    ${sender}    ${receiver}=    Customer Pair
    &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${1000}
    ${transfer}=    Api Request    POST    /transfers    ${sender}[token]    json=${body}
    Status Should Be    ${transfer}    400
    Error Code Should Be    ${transfer}    idempotency_key_required
    ${deposit}=    Admin Request    POST    /accounts/${sender}[account_id]/deposit    json=${{ {"amount_minor": 100} }}
    Status Should Be    ${deposit}    400
    Error Code Should Be    ${deposit}    idempotency_key_required

# ————————————————————————————————————————

Idempotency Key Format Is Validated
    [Tags]    contract    idempotency
    ${sender}    ${receiver}=    Customer Pair
    &{headers}=    Create Dictionary    Idempotency-Key=short
    &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${1000}
    ${response}=    Api Request    POST    /transfers    ${sender}[token]    json=${body}    headers=${headers}
    Status Should Be    ${response}    400
    Error Code Should Be    ${response}    idempotency_key_invalid

# ————————————————————————————————————————

Webhooks Can Be Registered And Listed
    [Tags]    webhooks
    ${created}=    Admin Request    POST    /webhooks    json=${{ {"url": "https://example.test/hook", "events": ["transfer.blocked", "fx.alert"]} }}
    Status Should Be    ${created}    201
    Should Not Be Empty    ${created}[body][secret]
    ${listed}=    Admin Request    GET    /webhooks
    Length Should Be    ${listed}[body][items]    1
    Should Not Contain    ${listed}[body][items][0]    secret
    ${invalid}=    Admin Request    POST    /webhooks    json=${{ {"url": "ftp://example.test/hook", "events": ["fx.alert"]} }}
    Status Should Be    ${invalid}    400
