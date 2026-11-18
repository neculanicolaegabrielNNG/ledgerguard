*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       api


*** Test Cases ***
Login Returns Token For Valid Credentials
    [Tags]    auth
    ${client}=    Create Funded Customer    RON    0
    &{body}=    Create Dictionary    email=${client}[email]    password=${client}[password]
    ${response}=    Api Request    POST    /auth/login    json=${body}
    Status Should Be    ${response}    200
    Should Be Equal    ${response}[body][role]    customer
    Should Not Be Empty    ${response}[body][access_token]

# ————————————————————————————————————————

Login Fails With Wrong Password
    [Tags]    auth
    ${client}=    Create Funded Customer    RON    0
    &{body}=    Create Dictionary    email=${client}[email]    password=wrong-password-1
    ${response}=    Api Request    POST    /auth/login    json=${body}
    Status Should Be    ${response}    401
    Error Code Should Be    ${response}    unauthorized

# ————————————————————————————————————————

Protected Route Requires Token
    [Tags]    auth
    ${response}=    Api Request    GET    /accounts
    Status Should Be    ${response}    401
    Error Code Should Be    ${response}    unauthorized

# ————————————————————————————————————————

Customer Cannot Access Admin Routes
    [Tags]    auth    roles
    ${client}=    Create Funded Customer    RON    0
    ${audit}=    Api Request    GET    /audit    ${client}[token]
    Status Should Be    ${audit}    403
    Error Code Should Be    ${audit}    forbidden
    ${shock}=    Api Request    POST    /fx/shock    ${client}[token]    json=${{ {"currency": "USD", "bps": 100} }}
    Status Should Be    ${shock}    403

# ————————————————————————————————————————

Compliance Cannot Create Customers
    [Tags]    auth    roles
    &{body}=    Create Dictionary    name=Test    email=x@test.local    password=long-enough-pass
    ${response}=    Compliance Request    POST    /customers    json=${body}
    Status Should Be    ${response}    403

# ————————————————————————————————————————

Customer Cannot Read Another Customers Account
    [Tags]    auth    roles
    ${first}    ${second}=    Customer Pair
    ${response}=    Api Request    GET    /accounts/${second}[account_id]    ${first}[token]
    Status Should Be    ${response}    403

# ————————————————————————————————————————

Error Response Has Standard Shape And Matching Correlation Id
    [Tags]    errors
    ${client}=    Create Funded Customer    RON    0
    ${response}=    Api Request    GET    /accounts/acc_missing    ${client}[token]
    Status Should Be    ${response}    404
    Error Code Should Be    ${response}    account_not_found
    ${error}=    Set Variable    ${response}[body][error]
    Dictionary Should Contain Key    ${error}    message
    Dictionary Should Contain Key    ${error}    details
    Should Be Equal    ${error}[correlation_id]    ${response}[headers][x-correlation-id]

# ————————————————————————————————————————

Supplied Correlation Id Reaches The Audit Trail
    [Tags]    errors    audit
    ${sender}    ${receiver}=    Customer Pair
    &{headers}=    Create Dictionary    Idempotency-Key=trace-key-0001    X-Correlation-ID=cid-trace-0001
    &{body}=    Create Dictionary    from_account_id=${sender}[account_id]    to_account_id=${receiver}[account_id]    amount_minor=${1000}
    ${response}=    Api Request    POST    /transfers    ${sender}[token]    json=${body}    headers=${headers}
    Status Should Be    ${response}    201
    Should Be Equal    ${response}[headers][x-correlation-id]    cid-trace-0001
    ${rows}=    Query    SELECT action FROM audit_log WHERE correlation_id = ?    cid-trace-0001
    ${actions}=    Evaluate    [row["action"] for row in $rows]
    Should Contain    ${actions}    transfer.created
    Should Contain    ${actions}    ledger.posted
    Should Contain    ${actions}    fraud.evaluated

# ————————————————————————————————————————

Validation Errors Use The Standard Shape
    [Tags]    errors
    ${client}=    Create Funded Customer    RON    0
    ${response}=    Api Request    POST    /accounts    ${client}[token]    json=${{ {"currency": "X"} }}
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    validation_failed

# ————————————————————————————————————————

Unsupported Currency Is Rejected
    [Tags]    errors
    ${client}=    Create Funded Customer    RON    0
    ${response}=    Api Request    POST    /accounts    ${client}[token]    json=${{ {"currency": "GBP"} }}
    Status Should Be    ${response}    422
    Error Code Should Be    ${response}    unsupported_currency

# ————————————————————————————————————————

Unknown Route Uses The Standard Shape
    [Tags]    errors
    ${response}=    Api Request    GET    /nothing-here
    Status Should Be    ${response}    404
    Error Code Should Be    ${response}    http_404

# ————————————————————————————————————————

Cursor Pagination Walks Every Account Exactly Once
    [Tags]    pagination
    ${client}=    Create Funded Customer    RON    0
    FOR    ${index}    IN RANGE    4
        Open Account    ${client}[token]    EUR
    END
    ${seen}=    Create List
    ${cursor}=    Set Variable    ${None}
    FOR    ${page}    IN RANGE    10
        &{params}=    Create Dictionary    limit=2
        IF    $cursor is not None
            Set To Dictionary    ${params}    cursor=${cursor}
        END
        ${response}=    Api Request    GET    /accounts    ${client}[token]    params=${params}
        Status Should Be    ${response}    200
        ${items}=    Set Variable    ${response}[body][items]
        FOR    ${item}    IN    @{items}
            Append To List    ${seen}    ${item}[id]
        END
        ${cursor}=    Set Variable    ${response}[body][next_cursor]
        IF    $cursor is None    BREAK
    END
    Length Should Be    ${seen}    5
    ${unique}=    Evaluate    len(set($seen))
    Should Be Equal As Integers    ${unique}    5

# ————————————————————————————————————————

Account List Filters By Currency
    [Tags]    pagination
    ${client}=    Create Funded Customer    RON    0
    Open Account    ${client}[token]    EUR
    ${response}=    Api Request    GET    /accounts    ${client}[token]    params=${{ {"currency": "EUR"} }}
    Status Should Be    ${response}    200
    Length Should Be    ${response}[body][items]    1

# ————————————————————————————————————————

Login Is Rate Limited
    [Tags]    rate_limit
    [Setup]    Start Fresh System    rate_limit_login=3
    ${statuses}=    Create List
    FOR    ${attempt}    IN RANGE    5
        &{body}=    Create Dictionary    email=nobody@test.local    password=wrong-password-1
        ${response}=    Api Request    POST    /auth/login    json=${body}
        Append To List    ${statuses}    ${response}[status]
    END
    Should Contain    ${statuses}    ${429}
    Should Be Equal As Integers    ${statuses}[0]    401
