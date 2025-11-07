# find-domain

Python CLI for brute-forcing short domain names against the GoDaddy availability API. Generate every n-letter combination for one or more TLDs, filter by price, and save the results to `available.json` without leaving the terminal.

## Prerequisites

- Python 3.9+
- GoDaddy API credentials for the OTE (test) environment
- `requests` (required) and `python-dotenv` (optional but recommended)

```bash
python -m pip install requests python-dotenv
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Getting GoDaddy API Credentials

1. Visit the [GoDaddy Developer Portal](https://developer.godaddy.com/keys/)
2. Sign in with your GoDaddy account
3. Click "Create New API Key"
4. Provide a name for your key (e.g., "Domain Lookup Script")
5. Select **"OTE" (Test Environment)** - this is important as the script uses the test API endpoint
6. Click "Create"
7. Copy your **API Key** and **API Secret** (you'll only see the secret once, so save it securely)

Create a `.env` file alongside `lookup.py` with:

```env
GODADDY_API_KEY=your_api_key_here
GODADDY_API_SECRET=your_api_secret_here
```

**Note:** The script uses the OTE (test) environment endpoint. For production use, you would need to modify the API endpoint in the script.

## Usage

### Basic Examples

Check all 3-letter `.com` domains:

```bash
python lookup.py 3
```

Check 3-letter domains for multiple TLDs:

```bash
python lookup.py 3 .com,.io,.net
```

Check 2-letter domains with a maximum price filter:

```bash
python lookup.py 2 .com --to 50
```

Check 3-letter domains with suffixes (e.g., `abc-app.com`, `abc-ai.com`):

```bash
python lookup.py 3 .com --suffixes -app,-ai
```

Show only available domains (quiet mode):

```bash
python lookup.py 3 .com --only-available
```

Verbose mode (shows full API responses):

```bash
python lookup.py 3 .com,.io --to 400 -v
```

### Command-Line Options

- `letters`: number of characters to generate (e.g. `3` produces `aaa`, `aab`, `aac`, ...)
- `tlds`: comma-separated list of TLDs. Defaults to `.com` if omitted.
- `--suffixes`: comma-separated suffixes appended before the TLD (e.g. `-ai,-app`). Defaults to no suffix.
- `--to`: optional upper bound on price in USD. Domains above this price will be filtered out.
- `-v/--verbose`: show full API responses and per-domain details.
- `--only-available`: limit console output to the green "available" domains (hides taken and too-expensive domains).
- `--batch-size`: number of domains to check per API request (default: 50, max: 50)
- `--delay`: delay in seconds between API requests (default: 2)

### Output Format

The script displays results in a clean format with colored dots:

- **Green dot (●)** - Domain is available
- **Red dot (●)** - Domain is taken
- **Yellow dot (●)** - Domain is available but exceeds the price filter

Example output:

```text
● abc.com
● xyz.com
● taken.com
```

In verbose mode (`-v`), the output also shows whether the availability status is **Definitive** or **Tentative**:

- **Definitive**: The availability check is conclusive
- **Tentative**: The status might not be final and may require further verification

### Understanding Available vs Definitive

The GoDaddy API returns two important fields:

- **`available`**: `true` if the domain can be registered, `false` if it's taken
- **`definitive`**: `true` if the availability status is conclusive, `false` if it's preliminary

When `definitive` is `false`, the availability result might not be final. The script uses `checkType=FULL` to get the most accurate results, but some domains may still return tentative status.

### JSON Output

The script automatically saves a running list of available domains to `available.json`, including any prices returned by the API. The JSON structure groups domains by TLD:

```json
{
  ".com": [{ "domain": "abc.com", "price": 12.99 }, { "domain": "xyz.com" }],
  ".io": [{ "domain": "abc.io", "price": 45.0 }]
}
```

Domains with `definitive: false` are marked in the JSON for reference. Interrupting the script with `Ctrl+C` triggers an immediate save before exiting, so you won't lose progress on long-running searches.
