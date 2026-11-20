# cli

How to Make It Work (Step-by-Step)
1. Create the Folder Structure
Create a main folder called datascrape on your computer, and create the exact subfolders and files inside it:

Plaintext
datascrape/                  <-- Main folder
├── pyproject.toml           <-- Paste Section 1 code here
└── datascrape/              <-- Subfolder with the same name
    ├── __init__.py          <-- Leave this file completely empty
    ├── http_client.py       <-- Paste Section 2 code here
    ├── storage.py           <-- Paste Section 7 code here
    ├── reports.py           <-- Paste Section 8 code here
    ├── cli.py               <-- Paste Section 9 code here
    └── clients/             <-- Subfolder
        ├── __init__.py      <-- Paste Section 6 code here
        ├── base.py          <-- Paste Section 3 code here
        ├── github.py        <-- Paste Section 4 code here
        └── bitbucket.py     <-- Paste Section 5 code here
(Note: That empty datascrape/__init__.py file is required so Python recognizes the folder as a package.)

2. Install It
Open your terminal (PowerShell, Command Prompt, or Mac/Linux Terminal), navigate into the top-level datascrape folder (the one containing pyproject.toml), and run:

Bash
pip install -e .
This installs the requests library automatically and registers the datascrape command. To verify it worked, run:

Bash
datascrape --help
If you see a list of options (--type, --url, --token, --report, etc.), it's installed and ready.

3. Get Your API Token
You need a Personal Access Token (PAT) from whichever platform you are scanning:

GitHub / GHES: Go to Settings -> Developer settings -> Personal access tokens -> Tokens (classic) and generate a token with repo and read:org scopes. (If your company uses SAML SSO, click Configure SSO next to the token and authorize it for your org.)

Bitbucket: Generate an App Password (Cloud) or HTTP Access Token (Server/DC) with read permissions for repositories and pull requests.

4. Run Your First Report
Replace YOUR_TOKEN and YOUR_ORG with your real values and run this in your terminal:

Bash
datascrape github \
  --type cloud \
  --url https://api.github.com \
  --token YOUR_TOKEN \
  --org YOUR_ORG \
  --report ownership_baseline \
  --output csv,json
(On Windows PowerShell, put it all on one line without the \ backslashes.)

5. Grab Your Results
When it finishes, look for a new reports/ folder in the directory where you ran the command. Inside, you'll find:

github_ownership_baseline.csv (open this in Excel to build your summary for Robertus)

github_ownership_baseline.json

github_ownership_baseline_errors.csv (only created if specific repos failed, so you can see what was skipped without losing the rest of the run)

Running the Other Deliverables
Just swap out --report for the other items on your list:

Apps & Service Accounts: --report apps_service_accounts

Archived & Inactive Repos: --report archived_inactive --inactive-days 180

Pull Request Metrics (with DB upsert): --report pull_request_metrics --db-path ./metrics.db --backfill-since 2026-01-01T00:00:00Z

Are you running this on Windows, Mac, or Linux? If you hit any errors during pip install -e ., paste the error here and we'll fix it.
