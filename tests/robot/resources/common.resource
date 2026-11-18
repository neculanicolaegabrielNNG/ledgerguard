*** Settings ***
Library     ApiLibrary.py
Library     DbLibrary.py
Library     Collections
Library     String
Variables   ../variables/config.py


*** Keywords ***
Start Fresh System
    [Arguments]    &{overrides}
    ${path}=    Start System    &{overrides}
    Connect To Db    ${path}
    RETURN    ${path}

# ————————————————————————————————————————

Stop Fresh System
    Disconnect Db
    Stop System

# ————————————————————————————————————————

Status Should Be
    [Arguments]    ${response}    ${expected}
    Should Be Equal As Integers    ${response}[status]    ${expected}    msg=Răspuns neașteptat: ${response}

# ————————————————————————————————————————

Error Code Should Be
    [Arguments]    ${response}    ${code}
    Should Be Equal    ${response}[body][error][code]    ${code}    msg=Răspuns neașteptat: ${response}

# ————————————————————————————————————————

Transfer State Should Be
    [Arguments]    ${response}    ${state}
    Status Should Be    ${response}    201
    Should Be Equal    ${response}[body][state]    ${state}    msg=Răspuns neașteptat: ${response}

# ————————————————————————————————————————

Customer Pair
    [Arguments]    ${currency}=RON    ${balance}=1000000    ${other_currency}=RON
    ${sender}=    Create Funded Customer    ${currency}    ${balance}
    ${receiver}=    Create Funded Customer    ${other_currency}    0
    RETURN    ${sender}    ${receiver}

# ————————————————————————————————————————

Open Case For Transfer
    [Arguments]    ${transfer_id}
    ${detail}=    Admin Request    GET    /transfers/${transfer_id}
    Status Should Be    ${detail}    200
    RETURN    ${detail}[body][case_id]

# ————————————————————————————————————————

Age Accounts
    Advance Clock    ${{ 8 * 86400 }}
    ${refresh}=    Refresh Fx
    Status Should Be    ${refresh}    200

# ————————————————————————————————————————

Update Rule
    [Arguments]    ${rule_id}    ${changes}
    ${response}=    Admin Request    PUT    /fraud/rules/${rule_id}    json=${changes}
    Status Should Be    ${response}    200
    RETURN    ${response}

# ————————————————————————————————————————

Disable Rule
    [Arguments]    ${rule_id}
    ${changes}=    Evaluate    {"active": False}
    Update Rule    ${rule_id}    ${changes}

# ————————————————————————————————————————

Make Review Rule
    ${changes}=    Evaluate    {"effect": "review", "params": {"amount_ron_minor": 1000}}
    Update Rule    R-NEW-BENEFICIARY    ${changes}

# ————————————————————————————————————————

Create Review Transfer
    [Arguments]    ${description}=
    Make Review Rule
    ${sender}    ${receiver}=    Customer Pair    RON    1000000
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    5000    ${description}
    Transfer State Should Be    ${response}    under_review
    RETURN    ${sender}    ${receiver}    ${response}[body][id]

# ————————————————————————————————————————

Triggered Types
    [Arguments]    ${transfer_id}
    ${detail}=    Admin Request    GET    /transfers/${transfer_id}
    Status Should Be    ${detail}    200
    ${types}=    Evaluate    [item["type"] for item in $detail["body"]["evaluation"]["results"] if item["triggered"]]
    RETURN    ${types}

# ————————————————————————————————————————

Send Transfer
    [Arguments]    ${sender}    ${receiver}    ${amount}    ${description}=
    ${response}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    ${amount}    ${description}
    Status Should Be    ${response}    201
    RETURN    ${response}

# ————————————————————————————————————————

Ledger Invariants Should Hold
    ${sums}=    Ledger Sums By Currency
    FOR    ${currency}    ${total}    IN    &{sums}
        Should Be Equal As Integers    ${total}    0    msg=Suma pe ${currency} nu este zero
    END
    ${unbalanced}=    Unbalanced Transactions
    Should Be Empty    ${unbalanced}
    ${negative}=    Customer Negative Balances
    Should Be Empty    ${negative}
