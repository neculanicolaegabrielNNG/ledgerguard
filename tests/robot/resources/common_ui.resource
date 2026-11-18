*** Settings ***
Library     Browser
Library     DbLibrary.py


*** Variables ***
${BASE_URL}    http://127.0.0.1:8000


*** Keywords ***
Open Ledgerguard
    Connect To Db    %{LEDGERGUARD_DB}
    New Browser    chromium    headless=${True}
    New Context
    New Page    ${BASE_URL}/login

# ————————————————————————————————————————

Login As
    [Arguments]    ${email}    ${password}
    Go To    ${BASE_URL}/login
    Fill Text    css=[data-testid=login-email] input    ${email}
    Fill Text    css=[data-testid=login-password] input    ${password}
    Click    css=[data-testid=login-submit]
    Wait For Elements State    css=[data-testid=session-email]    visible

# ————————————————————————————————————————

Logout
    Click    css=[data-testid=logout]
    Wait For Elements State    css=[data-testid=login-submit]    visible

# ————————————————————————————————————————

Select First Account
    [Arguments]    ${test_id}
    Click    css=[data-testid=${test_id}]
    Click    css=.q-menu .q-item >> nth=0

# ————————————————————————————————————————

Count Transfers
    ${count}=    Scalar    SELECT COUNT(*) FROM transfers
    RETURN    ${count}
