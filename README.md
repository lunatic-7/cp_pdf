# Codeforces PDF Generator

Create a PDF containing Codeforces problem statements from a list of URLs. The script saves each problem as a separate PDF and combines the successful ones into a single file. It keeps the statement, examples, formulas, and images while removing the surrounding website layout.

## Requirements

- Python 3.12
- An internet connection

## Setup

```bash
python -m venv venv
source venv/bin/activate
python -m pip install playwright pypdf
python -m playwright install chromium
```

On Windows, activate the environment with `venv\Scripts\activate` instead.

## Usage

Add one Codeforces problem URL per line to `problems.txt`:

```text
https://codeforces.com/problemset/problem/2274/B
https://codeforces.com/contest/2113/problem/B
```

Blank lines and lines starting with `#` are ignored. Both `codeforces.com` and `codeforces.me` links are supported.

`Try using codeforces.me, most of the time codeforces.com fails`

Run the generator from the project directory:

```bash
python main.py
```

The output is written to:

- `codeforces_problems.pdf` — all successfully generated problems, in input order
- `output/` — one PDF per problem

The script prints failed URLs as they occur and shows success and failure counts at the end. The local `completed_problems.txt` file and virtual environment are excluded from Git by `.gitignore`.
