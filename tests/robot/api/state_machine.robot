*** Settings ***
Resource         ../resources/common.resource
Test Setup       Start Fresh System
Test Teardown    Stop Fresh System
Force Tags       api    state_machine


*** Test Cases ***
Completed Transfer Has A Full Transition Trail
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${response}=    Send Transfer    ${sender}    ${receiver}    1000
    ${transfer_id}=    Set Variable    ${response}[body][id]
    ${rows}=    Query    SELECT from_state, to_state FROM transfer_transitions WHERE transfer_id = ? ORDER BY seq    ${transfer_id}
    ${states}=    Evaluate    [row["to_state"] for row in $rows]
    Should Be Equal    ${states}    ${{ ["created", "evaluated", "approved", "completed"] }}
    ${audited}=    Scalar    SELECT COUNT(*) FROM audit_log WHERE action = 'transfer.transition' AND entity_id = ?    ${transfer_id}
    Should Be Equal As Integers    ${audited}    3

# ————————————————————————————————————————

Completed Transfer Cannot Be Cancelled
    ${sender}    ${receiver}=    Customer Pair    RON    100000
    ${response}=    Send Transfer    ${sender}    ${receiver}    1000
    ${cancel}=    Api Request    POST    /transfers/${response}[body][id]/cancel    ${sender}[token]
    Status Should Be    ${cancel}    409
    Error Code Should Be    ${cancel}    invalid_transition
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    99000

# ————————————————————————————————————————

Review Transfer Holds Money Until Compliance Approves
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${held}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${held}    1000000
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${decision}=    Decide Case    ${case_id}    approve    Documentație verificată
    Status Should Be    ${decision}    200
    Should Be Equal    ${decision}[body][transfer][state]    completed
    ${after}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${after}    995000
    ${received}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${received}    5000
    Ledger Invariants Should Hold

# ————————————————————————————————————————

Review Transfer Blocked By Compliance Never Moves Money
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${decision}=    Decide Case    ${case_id}    block    Beneficiar suspect
    Status Should Be    ${decision}    200
    Should Be Equal    ${decision}[body][transfer][state]    blocked
    ${balance}=    Account Balance    ${sender}[token]    ${sender}[account_id]
    Should Be Equal As Integers    ${balance}    1000000
    ${entries}=    Scalar    SELECT COUNT(*) FROM transactions WHERE kind = 'transfer'
    Should Be Equal As Integers    ${entries}    0

# ————————————————————————————————————————

Decision Requires A Comment And A Known Action
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${short}=    Decide Case    ${case_id}    approve    ab
    Status Should Be    ${short}    422
    ${unknown}=    Decide Case    ${case_id}    maybe    Un comentariu valid
    Status Should Be    ${unknown}    422
    Error Code Should Be    ${unknown}    invalid_action

# ————————————————————————————————————————

Resolved Case Cannot Be Decided Again
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    Decide Case    ${case_id}    block    Beneficiar suspect
    ${again}=    Decide Case    ${case_id}    approve    Revenire asupra deciziei
    Status Should Be    ${again}    409
    Error Code Should Be    ${again}    case_already_resolved

# ————————————————————————————————————————

Escalation Keeps The Transfer Under Review
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${decision}=    Decide Case    ${case_id}    escalate    Necesită aviz juridic
    Status Should Be    ${decision}    200
    Should Be Equal    ${decision}[body][status]    escalated
    Should Be Equal    ${decision}[body][transfer][state]    under_review
    ${final}=    Decide Case    ${case_id}    block    Aviz primit
    Status Should Be    ${final}    200
    Should Be Equal    ${final}[body][transfer][state]    blocked

# ————————————————————————————————————————

Customer Can Cancel A Transfer Under Review
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${cancel}=    Api Request    POST    /transfers/${transfer_id}/cancel    ${sender}[token]
    Status Should Be    ${cancel}    200
    Should Be Equal    ${cancel}[body][state]    cancelled
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${late}=    Decide Case    ${case_id}    approve    Prea târziu pentru aprobare
    Status Should Be    ${late}    409
    ${resolution}=    Scalar    SELECT resolution FROM fraud_cases WHERE transfer_id = ?    ${transfer_id}
    Should Be Equal    ${resolution}    cancelled

# ————————————————————————————————————————

Blocked Transfer Cannot Be Completed By Any Route
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    Decide Case    ${case_id}    block    Beneficiar suspect
    ${retry}=    Decide Case    ${case_id}    approve    Încerc din nou aprobarea
    Status Should Be    ${retry}    409
    ${state}=    Scalar    SELECT state FROM transfers WHERE id = ?    ${transfer_id}
    Should Be Equal    ${state}    blocked

# ————————————————————————————————————————

Customers Cannot See The Compliance Queue
    ${client}=    Create Funded Customer    RON    0
    ${response}=    Api Request    GET    /fraud/cases    ${client}[token]
    Status Should Be    ${response}    403

# ————————————————————————————————————————

Blocking Emits A Webhook Event
    &{hook}=    Create Dictionary    url=https://example.test/hook    events=${{ ["transfer.blocked"] }}
    ${created}=    Admin Request    POST    /webhooks    json=${hook}
    Status Should Be    ${created}    201
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    Decide Case    ${case_id}    block    Beneficiar suspect
    ${pending}=    Query    SELECT event, status FROM webhook_deliveries
    Length Should Be    ${pending}    1
    Should Be Equal    ${pending}[0][event]    transfer.blocked
    Should Be Equal    ${pending}[0][status]    pending

# ————————————————————————————————————————

Decision Is Idempotent
    ${sender}    ${receiver}    ${transfer_id}=    Create Review Transfer
    ${case_id}=    Open Case For Transfer    ${transfer_id}
    ${key}=    New Key
    &{headers}=    Create Dictionary    Idempotency-Key=${key}
    &{body}=    Create Dictionary    action=approve    comment=Documentație verificată
    ${first}=    Compliance Request    POST    /fraud/cases/${case_id}/decision    json=${body}    headers=${headers}
    ${second}=    Compliance Request    POST    /fraud/cases/${case_id}/decision    json=${body}    headers=${headers}
    Status Should Be    ${first}    200
    Status Should Be    ${second}    200
    ${balance}=    Account Balance    ${receiver}[token]    ${receiver}[account_id]
    Should Be Equal As Integers    ${balance}    5000
