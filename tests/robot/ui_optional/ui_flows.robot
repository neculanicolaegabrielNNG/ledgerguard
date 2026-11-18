*** Settings ***
Documentation     Teste UI opționale. Necesită serverul pornit (scripts/run.ps1), robotframework-browser instalat și
...               inițializat (rfbrowser init) și variabilele de mediu LEDGERGUARD_DB, LEDGERGUARD_UI_PASSWORD,
...               LEDGERGUARD_UI_CUSTOMER, LEDGERGUARD_UI_COMPLIANCE, LEDGERGUARD_UI_TARGET_ACCOUNT.
Resource          ../resources/common_ui.resource
Suite Setup       Open Ledgerguard
Suite Teardown    Close Browser
Force Tags        ui_optional


*** Test Cases ***
Customer Transfer Goes From The Form To The Ledger
    Login As    %{LEDGERGUARD_UI_CUSTOMER}    %{LEDGERGUARD_UI_PASSWORD}
    Click    css=[data-testid=nav-transfer]
    Select First Account    transfer-from
    Fill Text    css=[data-testid=transfer-to] input    %{LEDGERGUARD_UI_TARGET_ACCOUNT}
    Fill Text    css=[data-testid=transfer-amount] input    1.00
    Fill Text    css=[data-testid=transfer-description] input    test ui
    ${before}=    Count Transfers
    Click    css=[data-testid=transfer-review]
    Click    css=[data-testid=transfer-confirm]
    Wait For Elements State    css=[data-testid=transfer-result]    visible
    ${text}=    Get Text    css=[data-testid=transfer-result]
    Should Not Be Empty    ${text}
    ${after}=    Count Transfers
    Should Be Equal As Integers    ${after}    ${{ ${before} + 1 }}
    Logout

# ————————————————————————————————————————

Compliance Reviews And Blocks A Case From The Console
    Login As    %{LEDGERGUARD_UI_COMPLIANCE}    %{LEDGERGUARD_UI_PASSWORD}
    Click    css=[data-testid=nav-queue]
    Wait For Elements State    css=[data-testid=queue-table]    visible
    Click    css=[data-testid=queue-table] tbody tr >> nth=0
    Wait For Elements State    css=[data-testid=case-analyze]    visible
    Click    css=[data-testid=case-analyze]
    Wait For Elements State    css=[data-testid=report-recommendation]    visible
    Fill Text    css=[data-testid=case-comment] input    Beneficiar suspect
    Click    css=[data-testid=case-block]
    Wait For Elements State    css=[data-testid=case-result]    visible
    ${blocked}=    Scalar    SELECT COUNT(*) FROM transfers WHERE state = 'blocked'
    Should Be True    ${blocked} >= 1
    Logout

# ————————————————————————————————————————

Network Graph Page Renders
    Login As    %{LEDGERGUARD_UI_COMPLIANCE}    %{LEDGERGUARD_UI_PASSWORD}
    Click    css=[data-testid=nav-graph]
    Wait For Elements State    css=[data-testid=network-graph]    visible
    Wait For Elements State    css=[data-testid=cluster-count]    visible
    Logout
