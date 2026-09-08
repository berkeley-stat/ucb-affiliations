# CLI Tool

A command-line tool for looking up user affiliations across multiple systems using CalNet UIDs.

**Requirements:** flowtoy >= 0.2.0

## Overview

This CLI tool queries multiple UC Berkeley systems to determine a user's department affiliations:

- **HR System**: Check for active employment in specific departments
- **SIS Academic Programs**: Check for enrollment in department programs
- **SIS Courses**: Check for enrollment in department courses
- **Grouper**: Check for group memberships in department folders

## Installation

```bash
pip install -e .
```

This installs the `affiliation-lookup` command, along with the external
tools it shells out to (`ucbhr`, `sis`, `grouper`, `ldapsearch-json`,
`calnet-resolve` - see the Dependencies section below).

## Environment Variables

Copy `.env.example` to `.env` and fill it in. Unlike the web app (which
loads `.env` automatically via `python-dotenv`), the CLI doesn't load it for
you - export it into your shell first:

```bash
set -a
source .env
set +a

affiliation-lookup 12345
```

Or, using `python-dotenv`'s own bundled CLI (note `--file` is a top-level
`dotenv` option, before the subcommand - not an option on `run` itself):

```bash
dotenv --file .env run -- affiliation-lookup 12345
```

You only need the external-system credential variables (`GROUPER_*`,
`UCBHR_*`, `SIS_*`, `CALNET_RESOLVE_*`) for the CLI - the Flask/OIDC ones in
`.env.example` are only used by the web app.

## Configuration

The tool requires a department configuration file (`config.yaml` by default) that specifies:

```yaml
department:
  name: "Example Department"
  hr_dept_numbers:
    - "12345"
    - "67890"
  academic_plan_codes:
    - "EXAMPBA"
    - "EXAMPMA"
  course_subject_areas:
    - "EXAMPLE"
  grouper_folder: "org:department:example"
```

## Usage

### Basic Usage

```bash
# Look up a user with status indicators
affiliation-lookup 12345
```

### Without Status Indicators

Useful for scripting or when you don't want the visual spinner:

```bash
affiliation-lookup 12345 --no-status
```

### Output Formats

#### Human-Readable (default)

```bash
affiliation-lookup 12345
```

Output:
```
Example Department - Affiliation Check
============================================================
User: 12345

Summary:
  Employee:                    YES
  Student:                     NO
  Enrolled in Department Courses: NO
  Group Member:                YES

Employment Details:
  - Assistant Professor (Example Department)

Group Memberships:
  - org:department:example:faculty
```

#### JSON Format

```bash
affiliation-lookup 12345 --format json
```

Output:
```json
{
  "calnet_uid": "12345",
  "department": "Example Department",
  "affiliations": {
    "employee": true,
    "student": false,
    "enrolled_in_courses": false,
    "group_member": true,
    "details": {
      "jobs": [
        {
          "title": "Assistant Professor",
          "department": "Example Department"
        }
      ],
      "programs": [],
      "courses": [],
      "groups": ["org:department:example:faculty"]
    }
  }
}
```

#### Bulk Format

Tab-separated values for bulk reporting:

```bash
affiliation-lookup 12345 --format bulk --no-status
```

Output:
```
12345	1	0	0	1
```

Fields: `calnet_uid`, `employee`, `student`, `enrolled_in_courses`, `group_member` (1=yes, 0=no)

### Custom Configuration File

```bash
affiliation-lookup 12345 --config /path/to/custom-config.yaml
```

### Exit Codes

- **0**: User has at least one affiliation
- **1**: User has no affiliations
- **2**: Error occurred during lookup

This is useful for scripting:

```bash
if affiliation-lookup 12345 --no-status; then
    echo "User is affiliated with the department"
else
    echo "User is not affiliated with the department"
fi
```

## Bulk Processing

Process multiple users:

```bash
# Create a list of UIDs
cat uids.txt
12345
67890
11111

# Look up all users
while read uid; do
    affiliation-lookup "$uid" --format bulk --no-status
done < uids.txt > results.tsv

# Or with a header
echo -e "uid\temployee\tstudent\tenrolled\tgroup_member" > results.tsv
while read uid; do
    affiliation-lookup "$uid" --format bulk --no-status
done < uids.txt >> results.tsv
```

## Dependencies

The CLI tool has minimal dependencies compared to the web application. `pip install -e .`
pulls in everything needed to run the flow, including the external tools it shells out to:

- **PyYAML**: Configuration file parsing
- **flowtoy**: Workflow orchestration
- **flowtoy-ldap**: LDAP directory lookups
- **ucbhr**: UC Berkeley HR system CLI
- **sis**: Student Information System CLI
- **grouper**: CalGroups/Grouper CLI
- **ldapsearch-json**: ldapsearch-alike, emits JSON
- **calnet-resolve**: CalNet shortname/UID resolution (needs `CALNET_RESOLVE_BIND_DN`
  and `CALNET_RESOLVE_BIND_PASSWORD` set - see that package's README)

No Flask, OIDC, or web server dependencies are required, and there are
currently no external tools outside of pip's control - `pip install -e .`
is sufficient.

You'll also need **LDAP access**: network reachability to `ldaps://ldap.berkeley.edu`.

See the flow configuration in `flow-uid.yaml`/`flow-shortname.yaml` for details.

## Comparison with Web Application

| Feature | Web App (ucb_affiliations.web) | CLI Tool (affiliation-lookup) |
|---------|-----------------|---------------------|
| Authentication | OIDC/CalNet | Direct UID input |
| User Interface | HTML/Browser | Terminal/Text |
| Status Indicators | Web page updates | Text spinner |
| Output Formats | HTML only | Human/JSON/Bulk |
| Dependencies | Flask, OIDC, etc. | Minimal (PyYAML, flowtoy) |
| Use Case | Interactive web use | Scripting, bulk processing |

## Examples

### Check if user is affiliated

```bash
affiliation-lookup 12345 --no-status
if [ $? -eq 0 ]; then
    echo "User is affiliated"
fi
```

### Generate report for all users

```bash
#!/bin/bash
echo "Generating department affiliation report..."

echo -e "uid\temployee\tstudent\tenrolled\tgroup_member" > report.tsv

for uid in $(cat user_list.txt); do
    affiliation-lookup "$uid" --format bulk --no-status >> report.tsv
done

echo "Report saved to report.tsv"
```

### Get detailed JSON output

```bash
affiliation-lookup 12345 --format json | jq '.affiliations.details.jobs'
```
