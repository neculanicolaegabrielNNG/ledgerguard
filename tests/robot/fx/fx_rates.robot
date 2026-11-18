*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       fx


*** Keywords ***
Current Rate
    [Arguments]    ${currency}
    ${rates}=    Admin Request    GET    /fx/rates
    Status Should Be    ${rates}    200
    ${rate}=    Evaluate    [item["rate_e8"] for item in $rates["body"]["items"] if item["currency"] == $currency][0]
    RETURN    ${rate}

# ————————————————————————————————————————

Expected Target Amount
    [Arguments]    ${amount}    ${source_rate}    ${target_rate}    ${spread_bps}
    ${expected}=    Evaluate    round(__import__("fractions").Fraction(${amount} * ${source_rate} * (10000 - ${spread_bps}), ${target_rate} * 10000))
    RETURN    ${expected}


*** Test Cases ***
Cross Currency Transfer Uses Current Rates And Configured Spread
    [Tags]    conversion
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    ${eur_rate}=    Current Rate    EUR
    ${usd_rate}=    Current Rate    USD
    ${expected}=    Expected Target Amount    100000    ${eur_rate}    ${usd_rate}    50
    ${response}=    Send Transfer    ${sender}    ${receiver}    100000
    Should Be Equal As Integers    ${response}[body][target_amount_minor]    ${expected}
    ${received}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${received}    ${expected}
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Cross Currency Transfer Posts Four Balanced Legs Through Exchange Accounts
    [Tags]    conversion
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    ${response}=    Send Transfer    ${sender}    ${receiver}    100000
    ${detail}=    Admin Request    GET    /transfers/${response}[body][id]
    ${transaction}=    Admin Request    GET    /ledger/transactions/${detail}[body][transaction_id]
    Length Should Be    ${transaction}[body][entries]    4
    ${currencies}=    Evaluate    sorted(entry["currency"] for entry in $transaction["body"]["entries"])
    Should Be Equal    ${currencies}    ${{ ["EUR", "EUR", "USD", "USD"] }}
    ${keys}=    Query    SELECT a.system_key FROM ledger_entries e JOIN accounts a ON a.id = e.account_id WHERE e.transaction_id = ? AND a.system_key IS NOT NULL    ${detail}[body][transaction_id]
    ${names}=    Evaluate    sorted(row["system_key"] for row in $keys)
    Should Be Equal    ${names}    ${{ ["FX-EUR", "FX-USD"] }}

# ————————————————————————————————————————

Rate Change After A Transaction Does Not Alter History
    [Tags]    history
    ${client}=    Create Funded Customer    USD    100000
    ${before}=    Query    SELECT amount_minor, amount_ron_minor, fx_rate_e8, fx_rate_id, fx_rate_at FROM ledger_entries WHERE account_id = ?    ${client}[account_id]
    Advance Clock    60
    Shock Fx    USD    500
    ${refresh}=    Refresh Fx
    ${applied}=    Evaluate    [item["currency"] for item in $refresh["body"]["applied"]]
    Should Contain    ${applied}    USD
    ${after}=    Query    SELECT amount_minor, amount_ron_minor, fx_rate_e8, fx_rate_id, fx_rate_at FROM ledger_entries WHERE account_id = ?    ${client}[account_id]
    Should Be Equal    ${before}    ${after}
    ${rates}=    Scalar    SELECT COUNT(*) FROM fx_rates WHERE base = 'USD'
    Should Be True    ${rates} >= 2
    Advance Clock    60
    ${second}=    Create Funded Customer    USD    100000
    ${new_row}=    Query    SELECT fx_rate_e8 FROM ledger_entries WHERE account_id = ?    ${second}[account_id]
    Should Not Be Equal As Integers    ${new_row}[0][fx_rate_e8]    ${before}[0][fx_rate_e8]

# ————————————————————————————————————————

Conversion Uses The Rate Valid At The Moment Of The Transaction
    [Tags]    history
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    ${first_rate}=    Current Rate    EUR
    ${first}=    Send Transfer    ${sender}    ${receiver}    10000
    Advance Clock    60
    Shock Fx    EUR    300
    Refresh Fx
    ${second_rate}=    Current Rate    EUR
    Should Not Be Equal As Integers    ${first_rate}    ${second_rate}
    ${second}=    Send Transfer    ${sender}    ${receiver}    10000
    ${rows}=    Query    SELECT e.fx_rate_e8 FROM ledger_entries e JOIN transactions t ON t.id = e.transaction_id WHERE t.transfer_id = ? AND e.account_id = ?    ${first}[body][id]    ${sender}[account_id]
    Should Be Equal As Integers    ${rows}[0][fx_rate_e8]    ${first_rate}
    ${rows}=    Query    SELECT e.fx_rate_e8 FROM ledger_entries e JOIN transactions t ON t.id = e.transaction_id WHERE t.transfer_id = ? AND e.account_id = ?    ${second}[body][id]    ${sender}[account_id]
    Should Be Equal As Integers    ${rows}[0][fx_rate_e8]    ${second_rate}

# ————————————————————————————————————————

Stale Rate Rejects New Conversions But Not Domestic Transfers
    [Tags]    stale
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    ${ron_sender}    ${ron_receiver}=    Customer Pair    RON    100000
    Advance Clock    ${{ 25 * 3600 }}
    ${rejected}=    Make Transfer    ${sender}[token]    ${sender}[account_id]    ${receiver}[account_id]    1000
    Status Should Be    ${rejected}    409
    Error Code Should Be    ${rejected}    fx_rate_stale
    ${domestic}=    Send Transfer    ${ron_sender}    ${ron_receiver}    1000
    Should Be Equal    ${domestic}[body][state]    completed
    ${rates}=    Admin Request    GET    /fx/rates
    ${statuses}=    Evaluate    {item["status"] for item in $rates["body"]["items"]}
    Should Be Equal    ${statuses}    ${{ {"stale"} }}
    Refresh Fx
    ${accepted}=    Send Transfer    ${sender}    ${receiver}    1000
    Should Be Equal    ${accepted}[body][state]    completed

# ————————————————————————————————————————

Absurd Rate Change Is Rejected And Raises An Alert
    [Tags]    absurd
    ${rate_before}=    Current Rate    USD
    Shock Fx    USD    5000
    ${refresh}=    Refresh Fx
    Status Should Be    ${refresh}    200
    ${rejected}=    Evaluate    [item["currency"] for item in $refresh["body"]["rejected"]]
    Should Contain    ${rejected}    USD
    ${rate_after}=    Current Rate    USD
    Should Be Equal As Integers    ${rate_before}    ${rate_after}
    ${alerts}=    Compliance Request    GET    /fx/alerts
    Status Should Be    ${alerts}    200
    Length Should Be    ${alerts}[body][items]    1
    Should Be Equal    ${alerts}[body][items][0][currency]    USD
    Should Be True    ${alerts}[body][items][0][change_bps] > 1000
    ${audited}=    Scalar    SELECT COUNT(*) FROM audit_log WHERE action = 'fx.rate_rejected'
    Should Be Equal As Integers    ${audited}    1

# ————————————————————————————————————————

Conversions Continue With The Last Accepted Rate After An Absurd Quote
    [Tags]    absurd
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    ${before}=    Current Rate    USD
    Shock Fx    USD    5000
    Refresh Fx
    ${response}=    Send Transfer    ${sender}    ${receiver}    10000
    ${rows}=    Query    SELECT e.fx_rate_e8 FROM ledger_entries e JOIN transactions t ON t.id = e.transaction_id WHERE t.transfer_id = ? AND e.currency = 'USD' LIMIT 1    ${response}[body][id]
    Should Be Equal As Integers    ${rows}[0][fx_rate_e8]    ${before}    msg=Cursul respins nu trebuie aplicat

# ————————————————————————————————————————

Moderate Rate Change Is Applied
    [Tags]    absurd
    Shock Fx    USD    500
    ${refresh}=    Refresh Fx
    ${applied}=    Evaluate    [item["currency"] for item in $refresh["body"]["applied"]]
    Should Contain    ${applied}    USD
    ${alerts}=    Compliance Request    GET    /fx/alerts
    Length Should Be    ${alerts}[body][items]    0

# ————————————————————————————————————————

Absurd Rate Change Emits A Webhook Event
    [Tags]    absurd    webhooks
    Admin Request    POST    /webhooks    json=${{ {"url": "https://example.test/hook", "events": ["fx.alert"]} }}
    Shock Fx    CHF    5000
    Refresh Fx
    ${events}=    Query    SELECT event FROM webhook_deliveries
    Length Should Be    ${events}    1
    Should Be Equal    ${events}[0][event]    fx.alert

# ————————————————————————————————————————

Repeated Conversions Neither Create Nor Destroy Money
    [Tags]    rounding
    [Setup]    Start Fresh System    fx_spread_bps=0
    ${client}=    Create Funded Customer    EUR    100000
    ${usd_account}=    Open Account    ${client}[token]    USD
    Disable Rule    R-CIRCULAR
    Disable Rule    R-VELOCITY
    FOR    ${index}    IN RANGE    15
        ${forward}=    Make Transfer    ${client}[token]    ${client}[account_id]    ${usd_account}    ${{ 1000 + ${index} * 7 }}
        Status Should Be    ${forward}    201
        ${usd}=    Account Balance    ${client}[token]    ${usd_account}
        ${back}=    Make Transfer    ${client}[token]    ${usd_account}    ${client}[account_id]    ${usd}
        Status Should Be    ${back}    201
    END
    ${final_eur}=    Account Balance    ${client}[token]    ${client}[account_id]
    ${final_usd}=    Account Balance    ${client}[token]    ${usd_account}
    Should Be Equal As Integers    ${final_usd}    0
    Should Be True    abs(${final_eur} - 100000) <= 30
    ${exchange_eur}=    System Balance    FX-EUR
    ${exchange_usd}=    System Balance    FX-USD
    Should Be Equal As Integers    ${{ ${final_eur} + ${exchange_eur} }}    100000
    Should Be Equal As Integers    ${{ ${final_usd} + ${exchange_usd} }}    0
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Spread Is Retained By The Exchange Accounts
    [Tags]    rounding
    ${sender}    ${receiver}=    Customer Pair    EUR    500000    USD
    Send Transfer    ${sender}    ${receiver}    100000
    ${exchange_eur}=    System Balance    FX-EUR
    Should Be Equal As Integers    ${exchange_eur}    100000
    ${exchange_usd}=    System Balance    FX-USD
    ${received}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${exchange_usd}    ${{ -${received} }}

# ————————————————————————————————————————

Simulated Provider Is Reproducible For A Fixed Seed
    [Tags]    provider
    [Setup]    Start Fresh System    fx_seed=7
    Refresh Fx
    Refresh Fx
    Refresh Fx
    ${first}=    Admin Request    GET    /fx/rates/history    params=${{ {"limit": 100} }}
    ${first_rates}=    Evaluate    [item["rate_e8"] for item in reversed($first["body"]["items"])]
    Stop Fresh System
    Start Fresh System    fx_seed=7
    Refresh Fx
    Refresh Fx
    Refresh Fx
    ${second}=    Admin Request    GET    /fx/rates/history    params=${{ {"limit": 100} }}
    ${second_rates}=    Evaluate    [item["rate_e8"] for item in reversed($second["body"]["items"])]
    Should Be Equal    ${first_rates}    ${second_rates}

# ————————————————————————————————————————

Frozen Provider Keeps Rates Constant
    [Tags]    provider
    ${before}=    Current Rate    EUR
    ${freeze}=    Admin Request    POST    /fx/freeze    json=${{ {"frozen": True} }}
    Status Should Be    ${freeze}    200
    Refresh Fx
    Refresh Fx
    ${after}=    Current Rate    EUR
    Should Be Equal As Integers    ${before}    ${after}

# ————————————————————————————————————————

Unreachable Optional Provider Falls Back To The Simulated Provider
    [Tags]    provider
    [Setup]    Start Fresh System    fx_provider=bnr    bnr_url=http://127.0.0.1:9/nbrfxrates.xml
    ${refresh}=    Refresh Fx
    Status Should Be    ${refresh}    200
    Should Be Equal    ${refresh}[body][source]    simulated
    Should Not Be Empty    ${refresh}[body][applied]

# ————————————————————————————————————————

Rate History Is Append Only And Paginated
    [Tags]    provider
    Refresh Fx
    Refresh Fx
    ${page}=    Admin Request    GET    /fx/rates/history    params=${{ {"limit": 2} }}
    Length Should Be    ${page}[body][items]    2
    Should Not Be Equal    ${page}[body][next_cursor]    ${None}
    ${by_currency}=    Admin Request    GET    /fx/rates/history    params=${{ {"currency": "EUR", "limit": 50} }}
    ${currencies}=    Evaluate    {item["base"] for item in $by_currency["body"]["items"]}
    Should Be Equal    ${currencies}    ${{ {"EUR"} }}
