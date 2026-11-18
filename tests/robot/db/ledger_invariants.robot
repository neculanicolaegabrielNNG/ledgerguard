*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       db    invariant


*** Test Cases ***
Ledger Sums To Zero Per Currency After Mixed Activity
    ${eur}    ${usd}=    Customer Pair    EUR    500000    USD
    ${ron}    ${other}=    Customer Pair    RON    300000
    Send Transfer    ${eur}    ${usd}    120000
    Send Transfer    ${ron}    ${other}    45000
    Send Transfer    ${eur}    ${usd}    333
    ${report}=    Compliance Request    GET    /ledger/invariants
    Status Should Be    ${report}    200
    Should Be True    ${report}[body][ok]
    Ledger Invariants Should Hold
    ${sums}=    Ledger Sums By Currency
    FOR    ${currency}    IN    RON    EUR    USD
        Should Be Equal As Integers    ${sums}[${currency}]    0
    END

# ————————————————————————————————————————

Every Transaction Is Balanced In Every Currency
    ${eur}    ${usd}=    Customer Pair    EUR    500000    USD
    Send Transfer    ${eur}    ${usd}    77777
    ${unbalanced}=    Unbalanced Transactions
    Should Be Empty    ${unbalanced}
    ${entries}=    Scalar    SELECT COUNT(*) FROM ledger_entries
    Should Be True    ${entries} >= 6

# ————————————————————————————————————————

Displayed Balance Equals Recomputed Balance
    ${sender}    ${receiver}=    Customer Pair    RON    250000
    Disable Rule    R-CIRCULAR
    Send Transfer    ${sender}    ${receiver}    11111
    Send Transfer    ${receiver}    ${sender}    1111
    FOR    ${client}    IN    ${sender}    ${receiver}
        ${displayed}=    Account Balance    ${client}[token]    ${client}[account_id]
        ${recomputed}=    Recomputed Balance    ${client}[account_id]
        Should Be Equal As Integers    ${displayed}    ${recomputed}
    END

# ————————————————————————————————————————

Total Customer Money Does Not Change After Same Currency Transfers
    ${sender}    ${receiver}=    Customer Pair    RON    250000
    Disable Rule    R-CIRCULAR
    ${before}=    Total Money    RON
    Send Transfer    ${sender}    ${receiver}    50000
    Send Transfer    ${receiver}    ${sender}    123
    ${after}=    Total Money    RON
    Should Be Equal As Integers    ${before}    ${after}
    Should Be Equal As Integers    ${after}    250000

# ————————————————————————————————————————

Ledger And Audit Tables Reject Update And Delete
    ${sender}    ${receiver}=    Customer Pair    RON    1000
    Send Transfer    ${sender}    ${receiver}    100
    FOR    ${statement}    IN
    ...    UPDATE ledger_entries SET amount_minor = amount_minor + 1
    ...    DELETE FROM ledger_entries
    ...    UPDATE transactions SET description = 'x'
    ...    DELETE FROM transactions
    ...    UPDATE audit_log SET action = 'x'
    ...    DELETE FROM audit_log
    ...    UPDATE fx_rates SET rate_e8 = 1
    ...    DELETE FROM fx_rates
    ...    UPDATE fraud_rules SET priority = 1
    ...    DELETE FROM fraud_rules
    ...    UPDATE fraud_evaluations SET score = 1
    ...    UPDATE transfer_transitions SET reason = 'x'
        ${message}=    Execute Expecting Error    ${statement}
        Should Contain    ${message}    append-only
    END

# ————————————————————————————————————————

Entry Currency Must Match The Account Currency
    ${client}=    Create Funded Customer    RON    0
    Execute Statement    INSERT INTO transactions (id, kind, correlation_id, created_at) VALUES ('t-x', 'deposit', 'c', 'now')
    ${message}=    Execute Expecting Error    INSERT INTO ledger_entries (transaction_id, account_id, currency, amount_minor, amount_ron_minor, fx_rate_e8, fx_rate_at, created_at) VALUES ('t-x', ?, 'EUR', 100, 497, 497000000, 'now', 'now')    ${client}[account_id]
    Should Contain    ${message}    currency

# ————————————————————————————————————————

Entries Store Original Amount Ron Equivalent And Rate Once
    ${client}=    Create Funded Customer    EUR    10000
    ${rows}=    Query    SELECT e.amount_minor, e.currency, e.amount_ron_minor, e.fx_rate_e8, e.fx_rate_id, e.fx_rate_at FROM ledger_entries e WHERE e.account_id = ?    ${client}[account_id]
    Length Should Be    ${rows}    1
    ${row}=    Set Variable    ${rows}[0]
    Should Be Equal As Integers    ${row}[amount_minor]    10000
    Should Be Equal    ${row}[currency]    EUR
    Should Not Be Equal    ${row}[fx_rate_id]    ${None}
    Should Not Be Empty    ${row}[fx_rate_at]
    ${expected}=    Evaluate    round(__import__("fractions").Fraction(10000 * $row["fx_rate_e8"], 10**8))
    Should Be Equal As Integers    ${row}[amount_ron_minor]    ${expected}

# ————————————————————————————————————————

Reversal Is A New Inverse Transaction That Restores Balances
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${sent}=    Send Transfer    ${sender}    ${receiver}    40000
    ${detail}=    Admin Request    GET    /transfers/${sent}[body][id]
    ${transaction_id}=    Set Variable    ${detail}[body][transaction_id]
    ${entries_before}=    Scalar    SELECT COUNT(*) FROM ledger_entries
    ${reversal}=    Admin Request    POST    /ledger/transactions/${transaction_id}/reverse    json=${{ {"reason": "Corecție operațională"} }}    headers=${{ {"Idempotency-Key": "reversal-0001-abc"} }}
    Status Should Be    ${reversal}    201
    ${entries_after}=    Scalar    SELECT COUNT(*) FROM ledger_entries
    Should Be Equal As Integers    ${entries_after}    ${{ ${entries_before} + 2 }}
    ${original_entries}=    Scalar    SELECT COUNT(*) FROM ledger_entries WHERE transaction_id = ?    ${transaction_id}
    Should Be Equal As Integers    ${original_entries}    2
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    100000
    ${kind}=    Scalar    SELECT kind FROM transactions WHERE reverses_id = ?    ${transaction_id}
    Should Be Equal    ${kind}    reversal
    ${again}=    Admin Request    POST    /ledger/transactions/${transaction_id}/reverse    json=${{ {"reason": "A doua corecție"} }}    headers=${{ {"Idempotency-Key": "reversal-0002-abc"} }}
    Status Should Be    ${again}    409
    Error Code Should Be    ${again}    already_reversed
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Money Columns Are Never Floating Point
    FOR    ${table}    IN    ledger_entries    transfers    fx_rates    scheduled_payments
        ${types}=    Query    SELECT name, type FROM pragma_table_info(?)    ${table}
        FOR    ${column}    IN    @{types}
            Should Not Be Equal    ${column}[type]    REAL    msg=${table}.${column}[name] este REAL
            Should Not Contain    ${column}[type]    FLOAT
            Should Not Contain    ${column}[type]    DOUBLE
        END
    END

# ————————————————————————————————————————

Every Money Movement Leaves An Audit Trail
    ${sender}    ${receiver}=    Customer Pair    RON    10000
    ${sent}=    Send Transfer    ${sender}    ${receiver}    1000
    ${actions}=    Query    SELECT action FROM audit_log WHERE entity_id = ? OR correlation_id = ?    ${sent}[body][id]    ${sent}[body][correlation_id]
    ${names}=    Evaluate    {row["action"] for row in $actions}
    Should Contain    ${names}    transfer.created
    Should Contain    ${names}    transfer.transition
    ${evaluation}=    Query    SELECT action FROM audit_log WHERE action = 'fraud.evaluated' AND entity_id = ?    ${sent}[body][id]
    Length Should Be    ${evaluation}    1

# ————————————————————————————————————————

Audit Search Filters By Entity And Text
    ${sender}    ${receiver}=    Customer Pair    RON    10000
    ${sent}=    Send Transfer    ${sender}    ${receiver}    1000
    ${by_entity}=    Admin Request    GET    /audit    params=${{ {"entity_id": $sent["body"]["id"]} }}
    Status Should Be    ${by_entity}    200
    Should Not Be Empty    ${by_entity}[body][items]
    ${by_text}=    Admin Request    GET    /audit    params=${{ {"q": "fraud.evaluated"} }}
    Status Should Be    ${by_text}    200
    Should Not Be Empty    ${by_text}[body][items]
